"""Tests de integración: qué puede hacer el rol `anon` sobre el esquema público.

La anon key es pública por diseño —viaja al navegador y cualquiera la lee— así
que los privilegios del rol `anon` son, literalmente, lo que puede hacer un
desconocido contra la base de datos a través de PostgREST.

Supabase otorga ALL sobre cada tabla nueva de `public` a `anon` por default
privileges, y las tablas del pipeline no tienen RLS que lo contenga. La
migración 0014 cierra eso; estos tests son su criterio de aceptación y la red
que impide que una migración futura lo reabra sin que nadie se entere.

Ejecutar con: pytest -m integration -v tests/test_privilegios_anon.py
"""

import os

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

pytestmark = pytest.mark.integration

_ESCRITURA = ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]

# Tablas del pipeline y de infraestructura: no las lee el navegador, las lee
# Astro en el servidor con la service key. `anon` no tiene nada que hacer aquí.
_TABLAS_INTERNAS = [
    "alembic_version",
    "scrape_runs",
    "run_fail_logs",
    "ia_runs",
    "deals",
    "autocosmos_listings",
    "yapo_listings",
    "autosusados_listings",
    "checkeados_listings",
]

skip_sin_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL no configurada"
)
skip_sin_anon = pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and os.getenv("PUBLIC_SUPABASE_ANON_KEY")),
    reason="SUPABASE_URL o PUBLIC_SUPABASE_ANON_KEY no configuradas",
)


@pytest_asyncio.fixture
async def conexion():
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


@pytest.fixture
def cliente_anon():
    anon = os.environ["PUBLIC_SUPABASE_ANON_KEY"].strip()
    return httpx.AsyncClient(
        base_url=f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1",
        headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
        timeout=15,
    )


async def _tablas_publicas(conexion) -> list[str]:
    filas = await conexion.execute(
        text(
            """SELECT c.relname FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'public' AND c.relkind = 'r'
               ORDER BY c.relname"""
        )
    )
    return [f[0] for f in filas]


# ── Privilegios en el catálogo ───────────────────────────────────────────────


@skip_sin_db
async def test_anon_no_escribe_en_ninguna_tabla(conexion):
    """Ninguna tabla de `public` puede ser escrita por un anónimo.

    Las tablas de particulares se escriben con la sesión del usuario, que es el
    rol `authenticated`, no `anon`. Para `anon` no hay ningún caso legítimo de
    escritura en todo el esquema.
    """
    ofensores = []
    for tabla in await _tablas_publicas(conexion):
        for privilegio in _ESCRITURA:
            tiene = await conexion.scalar(
                text("SELECT has_table_privilege('anon', :t, :p)"),
                {"t": f"public.{tabla}", "p": privilegio},
            )
            if tiene:
                ofensores.append(f"{tabla}:{privilegio}")

    assert not ofensores, f"anon puede escribir en: {', '.join(ofensores)}"


@skip_sin_db
@pytest.mark.parametrize("tabla", _TABLAS_INTERNAS)
async def test_anon_no_lee_las_tablas_internas(conexion, tabla):
    """El catálogo se sirve por SSR con la service key, no exponiendo las tablas.

    Dárselas a `anon` convierte a PostgREST en un export masivo del scraping
    ajeno a la web, y en el caso de scrape_runs/alembic_version filtra detalle
    operativo del pipeline.
    """
    tiene = await conexion.scalar(
        text("SELECT has_table_privilege('anon', :t, 'SELECT')"),
        {"t": f"public.{tabla}"},
    )

    assert tiene is False, f"anon puede leer public.{tabla}"


@skip_sin_db
async def test_los_privilegios_por_defecto_estan_cerrados(conexion):
    """La próxima tabla que cree Alembic no debe nacer abierta.

    Sin esto el arreglo dura hasta el siguiente `create_table`: es la parte que
    evita tener que repetir la migración 0014 cada vez.

    Se acota a las default privileges cuyo dueño es `postgres` porque son las
    únicas que gobiernan a este proyecto —todas las tablas de `public` son suyas—
    y las únicas que podemos modificar: Supabase mantiene otra entrada a nombre
    de `supabase_admin`, rol del que `postgres` no es miembro ni superusuario.
    Una tabla creada por ese rol (p. ej. desde el panel de Supabase) sí nacería
    abierta, y hay que cerrarla a mano.
    """
    filas = await conexion.execute(
        text(
            """SELECT defaclacl::text FROM pg_default_acl d
               JOIN pg_namespace n ON n.oid = d.defaclnamespace
               WHERE n.nspname = 'public' AND d.defaclobjtype = 'r'
                 AND d.defaclrole = cast('postgres' AS regrole)"""
        )
    )
    acls = [f[0] for f in filas]

    concedidos = [a for a in acls if "anon=" in a or "authenticated=" in a]
    assert not concedidos, f"default privileges siguen abriendo tablas nuevas: {concedidos}"


# ── Comprobación desde fuera, con la anon key ────────────────────────────────


@skip_sin_anon
@pytest.mark.parametrize("tabla", ["autocosmos_listings", "yapo_listings", "deals"])
async def test_la_api_publica_rechaza_borrar(cliente_anon, tabla):
    """El test que importa: intentar borrar de verdad, como lo haría un atacante.

    El filtro `id=eq.-1` no coincide con ninguna fila (los id son autoincrement
    desde 1), así que la prueba es inocua aunque el permiso exista: lo que se
    mide es si PostgREST autoriza la operación, no su efecto.
    """
    async with cliente_anon as cliente:
        respuesta = await cliente.delete(f"/{tabla}", params={"id": "eq.-1"})

    assert respuesta.status_code in (401, 403), (
        f"anon pudo ejecutar DELETE sobre {tabla} (HTTP {respuesta.status_code})"
    )


@skip_sin_anon
@pytest.mark.parametrize("tabla", ["scrape_runs", "alembic_version"])
async def test_la_api_publica_no_expone_tablas_internas(cliente_anon, tabla):
    """Ni las métricas del pipeline ni la versión del esquema son públicas."""
    async with cliente_anon as cliente:
        respuesta = await cliente.get(f"/{tabla}", params={"limit": 1})

    assert respuesta.status_code in (401, 403, 404), (
        f"{tabla} legible por anon: HTTP {respuesta.status_code} {respuesta.text[:120]}"
    )
