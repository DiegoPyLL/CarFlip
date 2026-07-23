"""Tests de integración del perfil de usuario y su blindaje RLS.

Las cinco tablas de particulares las escribe la web con la anon key del propio
usuario, no el pipeline: la única autorización que existe son las políticas RLS
y los GRANT de la migración 0010. Un `ENABLE ROW LEVEL SECURITY` que se caiga
en un rollback deja teléfonos de usuarios legibles por cualquiera a través de
PostgREST, y nada en el código Python lo notaría.

Por eso estos tests se leen contra el Supabase real y son de solo lectura:
interrogan el catálogo (`pg_policies`, `pg_class`, `information_schema`) y
comprueban desde fuera, con la anon key, que la API pública no devuelve lo que
no debe.

Ejecutar con: pytest -m integration -v tests/test_perfiles_rls.py
"""

import os

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

pytestmark = pytest.mark.integration

_TIMEOUT = 15

_TABLAS_PROTEGIDAS = [
    "perfiles",
    "particulares_listings",
    "particulares_fotos",
    "contacto_revelaciones",
    "reportes_aviso",
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
    """Conexión de solo lectura al Postgres de producción.

    Motor propio y desechable: el `engine` global del proyecto cachea
    conexiones atadas al event loop del primer test que lo usa.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


@pytest.fixture
def cliente_anon():
    """Cliente HTTP contra PostgREST con la anon key, igual que el navegador."""
    anon = os.environ["PUBLIC_SUPABASE_ANON_KEY"].strip()
    return httpx.AsyncClient(
        base_url=f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1",
        headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
        timeout=_TIMEOUT,
    )


# ── Blindaje del esquema ─────────────────────────────────────────────────────


@skip_sin_db
@pytest.mark.parametrize("tabla", _TABLAS_PROTEGIDAS)
async def test_rls_habilitado(conexion, tabla):
    """Sin RLS activo las políticas no se evalúan y la tabla queda abierta."""
    activo = await conexion.scalar(
        text("SELECT relrowsecurity FROM pg_class WHERE oid = cast(:t AS regclass)"),
        {"t": f"public.{tabla}"},
    )

    assert activo is True, f"public.{tabla} sin ROW LEVEL SECURITY"


@skip_sin_db
@pytest.mark.parametrize("tabla", _TABLAS_PROTEGIDAS)
async def test_cada_tabla_tiene_politicas(conexion, tabla):
    """RLS activo sin políticas niega todo; con políticas, define quién ve qué."""
    n = await conexion.scalar(
        text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=:t"),
        {"t": tabla},
    )

    assert n > 0, f"public.{tabla} tiene RLS pero ninguna política"


@skip_sin_db
async def test_anon_no_tiene_ningun_permiso_sobre_perfiles(conexion):
    """El teléfono del usuario no puede salir por la API pública.

    `perfiles` es la única tabla sin GRANT a anon: PostgREST no expone una tabla
    que el rol no puede tocar, así que este es el primer candado, antes de RLS.
    """
    permisos = await conexion.scalar(
        text(
            """SELECT count(*) FROM information_schema.role_table_grants
               WHERE table_schema='public' AND table_name='perfiles' AND grantee='anon'"""
        )
    )

    assert permisos == 0, "anon tiene permisos sobre perfiles"


@skip_sin_db
async def test_authenticated_lee_y_edita_perfiles_pero_no_los_crea_ni_borra(conexion):
    """El alta y la baja del perfil son del trigger y del CASCADE, no del usuario."""
    filas = await conexion.execute(
        text(
            """SELECT privilege_type FROM information_schema.role_table_grants
               WHERE table_schema='public' AND table_name='perfiles'
                 AND grantee='authenticated'"""
        )
    )
    privilegios = {f[0] for f in filas}

    assert privilegios == {"SELECT", "UPDATE"}


@skip_sin_db
@pytest.mark.parametrize(
    "politica", ["perfiles_select_propio", "perfiles_update_propio"]
)
async def test_politicas_de_perfil_son_por_dueno(conexion, politica):
    """Ambas políticas comparan contra auth.uid(): nadie ve el perfil de otro."""
    fila = await conexion.execute(
        text(
            """SELECT roles::text, qual, with_check FROM pg_policies
               WHERE schemaname='public' AND tablename='perfiles' AND policyname=:p"""
        ),
        {"p": politica},
    )
    roles, qual, with_check = fila.one()

    assert "authenticated" in roles
    assert "anon" not in roles
    assert "auth.uid()" in qual
    if with_check is not None:
        assert "auth.uid()" in with_check


@skip_sin_db
async def test_trigger_crea_el_perfil_al_registrarse(conexion):
    """Todo usuario nuevo nace con perfil; si el trigger falta, la web rompe al publicar."""
    existe = await conexion.scalar(
        text(
            """SELECT count(*) FROM pg_trigger t
               JOIN pg_class c ON c.oid = t.tgrelid
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname='auth' AND c.relname='users'
                 AND t.tgname='crear_perfil_al_registrarse' AND NOT t.tgisinternal"""
        )
    )

    assert existe == 1, "falta el trigger crear_perfil_al_registrarse en auth.users"


@skip_sin_db
async def test_la_funcion_del_trigger_esta_endurecida(conexion):
    """SECURITY DEFINER con search_path vacío: no se la puede desviar por shadowing.

    Una función SECURITY DEFINER sin search_path fijo es escalación de
    privilegios de manual, y esta corre con cada registro de usuario.
    """
    fila = await conexion.execute(
        text(
            """SELECT p.prosecdef, p.proconfig FROM pg_proc p
               JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname='public' AND p.proname='crear_perfil_para_usuario'"""
        )
    )
    security_definer, config = fila.one()

    assert security_definer is True
    assert config is not None and "search_path=" in " ".join(config)


@skip_sin_db
async def test_el_perfil_cae_con_la_cuenta(conexion):
    """Borrar la cuenta debe llevarse el perfil: es un requisito de datos personales."""
    fila = await conexion.execute(
        text(
            """SELECT confdeltype::text FROM pg_constraint
               WHERE conname='fk_perfiles_auth_users'
                 AND conrelid = cast('public.perfiles' AS regclass)"""
        )
    )

    assert fila.scalar_one() == "c", "la FK contra auth.users no es ON DELETE CASCADE"


# ── Vista desde fuera, con la anon key ───────────────────────────────────────


@skip_sin_anon
async def test_la_api_publica_no_expone_perfiles(cliente_anon):
    """El chequeo que de verdad importa: pedirle perfiles a PostgREST como anónimo."""
    async with cliente_anon as cliente:
        respuesta = await cliente.get("/perfiles", params={"select": "*"})

    assert respuesta.status_code != 200, f"perfiles legible por anon: {respuesta.text[:200]}"
    assert "telefono" not in respuesta.text


@skip_sin_anon
async def test_la_api_publica_sirve_el_catalogo_sin_sesion(cliente_anon):
    """La contracara: el catálogo público sí debe responder sin sesión."""
    async with cliente_anon as cliente:
        respuesta = await cliente.get(
            "/particulares_listings", params={"select": "id,estado", "limit": 5}
        )

    assert respuesta.status_code == 200, respuesta.text[:200]
    assert all(a["estado"] == "publicado" for a in respuesta.json())


@skip_sin_anon
async def test_la_api_publica_esconde_los_avisos_no_publicados(cliente_anon):
    """Pausados y vendidos no salen a la calle.

    Se pregunta por lo que NO debe verse en vez de revisar lo que vino: así el
    test sigue siendo concluyente aunque la tabla esté vacía.
    """
    async with cliente_anon as cliente:
        respuesta = await cliente.get(
            "/particulares_listings",
            params={"select": "id,estado", "estado": "neq.publicado"},
        )

    assert respuesta.status_code == 200, respuesta.text[:200]
    assert respuesta.json() == [], "RLS deja ver avisos no publicados a un anónimo"


@skip_sin_anon
async def test_anon_no_puede_publicar_avisos(cliente_anon):
    """Publicar exige sesión: sin ella el INSERT lo rechaza el grant o la política."""
    async with cliente_anon as cliente:
        respuesta = await cliente.post(
            "/particulares_listings",
            json={
                "id_externo": "test-rls-anon",
                "url": "https://carflip.cl/auto/p/test",
                "titulo": "Intento anónimo",
                "usuario_id": "00000000-0000-0000-0000-000000000000",
            },
        )

    assert respuesta.status_code in (401, 403), f"anon pudo insertar: {respuesta.status_code}"
