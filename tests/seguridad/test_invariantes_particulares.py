"""Tests de integración: qué invariantes de los avisos de particulares hace cumplir la base.

`particulares_listings` la escribe el navegador con la sesión del usuario (anon key
+ JWT), así que PostgREST es alcanzable sin pasar por `/api/publicacion`: toda
validación que viva solo en `formulario.ts` o `limites.ts` es evitable con una
sola petición. La migración 0018 mueve los invariantes acá; estos tests son su
criterio de aceptación y la red que impide que una migración futura los deshaga
sin que nadie se entere.

Son de solo lectura: interrogan el catálogo, no insertan nada.

Ejecutar con: pytest -m integration -v tests/seguridad/test_invariantes_particulares.py
"""

import os

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

pytestmark = pytest.mark.integration

_TABLA = "particulares_listings"

# Columnas que la aplicación nunca escribe y que dan ventaja a quien las escriba:
# `vistas` es el contador de interés, `publicado_en` sostiene el tope de 15 por
# 24 h, `ultima_vez_visto` es la clave del orden "reciente" de /avisos (fijarla en
# el futuro clava el aviso arriba del listado), y `url` es el enlace del aviso.
_COLUMNAS_VEDADAS = ["vistas", "publicado_en", "primera_vez_visto", "moneda", "fecha_publicacion"]

_CHECKS_ESPERADOS = [
    "ck_particulares_estado",
    "ck_particulares_precio",
    "ck_particulares_km",
    "ck_particulares_anio",
    "ck_particulares_vistas",
    "ck_particulares_titulo_largo",
    "ck_particulares_descripcion_largo",
    "ck_particulares_patente",
]

_TRIGGERS_ESPERADOS = ["particulares_deriva_campos", "particulares_topes"]

_UNIQUES_ESPERADOS = [
    ("contacto_revelaciones", "uq_contacto_revelaciones_aviso_usuario"),
    ("reportes_aviso", "uq_reportes_aviso_aviso_usuario"),
]

skip_sin_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL no configurada"
)


@pytest_asyncio.fixture
async def conexion():
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


# ── Dominios de valor ────────────────────────────────────────────────────────


@skip_sin_db
@pytest.mark.parametrize("restriccion", _CHECKS_ESPERADOS)
async def test_los_check_del_aviso_existen(conexion, restriccion):
    """Sin CHECK, un POST directo mete precios negativos, años imposibles o un
    `estado` inventado que deja el aviso fuera de toda vista de moderación."""
    existe = await conexion.scalar(
        text(
            """SELECT count(*) FROM pg_constraint c
               JOIN pg_class t ON t.oid = c.conrelid
               WHERE t.relname = :tabla AND c.conname = :nombre AND c.contype = 'c'"""
        ),
        {"tabla": _TABLA, "nombre": restriccion},
    )

    assert existe == 1, f"falta la restricción {restriccion} en {_TABLA}"


@skip_sin_db
@pytest.mark.parametrize("tabla,restriccion", _UNIQUES_ESPERADOS)
async def test_una_vez_por_aviso_y_usuario(conexion, tabla, restriccion):
    """`yaReveloContacto` y `yaReportoAviso` comprueban antes de insertar, pero
    eso es una carrera —y por PostgREST directo no hay comprobación alguna—: sin
    el unique, un usuario infla los reportes de un aviso o el contador de interés
    del vendedor."""
    existe = await conexion.scalar(
        text(
            """SELECT count(*) FROM pg_constraint c
               JOIN pg_class t ON t.oid = c.conrelid
               WHERE t.relname = :tabla AND c.conname = :nombre AND c.contype = 'u'"""
        ),
        {"tabla": tabla, "nombre": restriccion},
    )

    assert existe == 1, f"falta el unique {restriccion} en {tabla}"


# ── Privilegios por columna ──────────────────────────────────────────────────


@skip_sin_db
@pytest.mark.parametrize("columna", _COLUMNAS_VEDADAS)
@pytest.mark.parametrize("privilegio", ["INSERT", "UPDATE"])
async def test_authenticated_no_escribe_las_columnas_que_no_le_toca(conexion, columna, privilegio):
    """Un GRANT de tabla completa alcanza a toda columna presente y futura, así
    que los privilegios van columna por columna. RLS no cubre esto: la política
    autoriza la fila, no qué campos de la fila."""
    tiene = await conexion.scalar(
        text("SELECT has_column_privilege('authenticated', :t, :c, :p)"),
        {"t": f"public.{_TABLA}", "c": columna, "p": privilegio},
    )

    assert tiene is False, f"authenticated puede hacer {privilegio} de {_TABLA}.{columna}"


@skip_sin_db
async def test_authenticated_sigue_pudiendo_publicar_y_editar(conexion):
    """La contracara: acotar por columna no debe haber roto el formulario."""
    faltantes = []
    for columna in ["marca", "modelo", "anio", "km", "precio", "estado", "descripcion"]:
        for privilegio in ["INSERT", "UPDATE"]:
            tiene = await conexion.scalar(
                text("SELECT has_column_privilege('authenticated', :t, :c, :p)"),
                {"t": f"public.{_TABLA}", "c": columna, "p": privilegio},
            )
            if not tiene:
                faltantes.append(f"{columna}:{privilegio}")

    assert not faltantes, f"el formulario no podría escribir: {', '.join(faltantes)}"


# ── Triggers ─────────────────────────────────────────────────────────────────


@skip_sin_db
@pytest.mark.parametrize("trigger", _TRIGGERS_ESPERADOS)
async def test_los_triggers_del_aviso_existen_y_estan_activos(conexion, trigger):
    """Derivar `titulo`/`url`/`disponible` y aplicar el tope diario es lo que hace
    que los límites de la aplicación signifiquen algo para quien no pasa por ella.
    `tgenabled = 'O'` es el estado normal (activo en modo origin); la columna es
    del tipo `"char"`, que el driver entrega como bytes."""
    estado = await conexion.scalar(
        text(
            """SELECT tg.tgenabled FROM pg_trigger tg
               JOIN pg_class t ON t.oid = tg.tgrelid
               WHERE t.relname = :tabla AND tg.tgname = :nombre AND NOT tg.tgisinternal"""
        ),
        {"tabla": _TABLA, "nombre": trigger},
    )

    assert estado == b"O", f"el trigger {trigger} falta o está deshabilitado (tgenabled={estado!r})"


# ── Funciones ────────────────────────────────────────────────────────────────


@skip_sin_db
async def test_ninguna_funcion_publica_es_invocable_por_anon(conexion):
    """En PostgreSQL toda función nace con EXECUTE para PUBLIC, así que sin
    revocarlo `anon` puede invocar por PostgREST cualquier función del esquema,
    incluidas las SECURITY DEFINER que existen justamente para saltarse RLS."""
    filas = await conexion.execute(
        text(
            """SELECT p.proname FROM pg_proc p
               JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname = 'public'
                 AND (has_function_privilege('anon', p.oid, 'EXECUTE')
                      OR has_function_privilege('authenticated', p.oid, 'EXECUTE'))
               ORDER BY p.proname"""
        )
    )
    invocables = [f[0] for f in filas]

    assert not invocables, f"anon/authenticated pueden ejecutar: {', '.join(invocables)}"


@skip_sin_db
async def test_los_privilegios_por_defecto_de_funciones_estan_cerrados(conexion):
    """Igual que con las tablas en la 0014: sin cerrar el default, la próxima
    función que cree una migración vuelve a nacer invocable."""
    filas = await conexion.execute(
        text(
            """SELECT defaclacl::text FROM pg_default_acl d
               JOIN pg_namespace n ON n.oid = d.defaclnamespace
               WHERE n.nspname = 'public' AND d.defaclobjtype = 'f'
                 AND d.defaclrole = cast('postgres' AS regrole)"""
        )
    )
    concedidos = [a[0] for a in filas if "anon=" in a[0] or "authenticated=" in a[0]]

    assert not concedidos, f"default privileges siguen abriendo funciones nuevas: {concedidos}"


@skip_sin_db
async def test_el_rate_limit_de_contacto_lo_aplica_la_base(conexion):
    """Contar y después insertar desde la web era una carrera, y la fila se
    insertaba incluso al superar el tope. La función de la 0019 decide y escribe
    en el mismo statement, serializada por IP."""
    existe = await conexion.scalar(
        text(
            """SELECT count(*) FROM pg_proc p
               JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname = 'public'
                 AND p.proname = 'registrar_solicitud_contacto'
                 AND p.prosecdef"""
        )
    )

    assert existe == 1, "falta la función registrar_solicitud_contacto (o no es SECURITY DEFINER)"
