"""Usuarios y clientes desechables para probar la creación de avisos contra Supabase.

Las cinco tablas de particulares las escribe el navegador con la anon key más el
JWT del usuario, no el pipeline: la autorización es RLS y nada más. Eso solo se
puede probar contra Supabase de verdad, porque `auth.uid()` y el rol
`authenticated` no existen en un PostgreSQL pelado. Por eso esta suite es la
excepción a la regla del `conftest.py` de la raíz —que manda las escrituras a una
BD desechable— y por eso está cerrada con llave:

- No corre salvo que se pase `--supabase` (o se exporte `CARFLIP_TEST_SUPABASE=1`).
  Un `pytest` normal no abre una sola conexión, aunque el `.env` tenga las
  credenciales cargadas.
- Todo lo que crea lleva `id_externo` con el prefijo `test-pytest-` y el título
  empieza con `[TEST]`, para reconocerlo de un vistazo si algo se escapa.
- Los usuarios son desechables (`carflip-test-*@example.com`) y se borran en el
  `finally`; el CASCADE se lleva perfil y avisos.
- Antes y después de la sesión se barren los restos de cualquier corrida que se
  haya caído a medias.

Ejecutar con:

    pytest -m integration -v tests/publicaciones/ --supabase
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

# ── Etiquetas ────────────────────────────────────────────────────────────────
# `id_externo` es la etiqueta fiable: es NOT NULL, UNIQUE y ningún test lo
# machaca. El `[TEST]` del título es para el ojo humano, y los tests que meten
# basura en el título lo pierden a propósito; por eso la limpieza no se apoya en
# él.
ETIQUETA = "[TEST]"
PREFIJO_EXTERNO = "test-pytest-"
PREFIJO_EMAIL = "carflip-test-"

# Cabecera que pide a PostgREST devolver las filas afectadas. Sin ella, un PATCH
# o un DELETE que RLS deja en cero responde 204 igual que uno que sí tocó algo.
PREFER = {"Prefer": "return=representation"}

_OPT_IN = "CARFLIP_TEST_SUPABASE"
_TIMEOUT = 20
_CLAVE = "CarFlip-Test-2026!"
_VARIABLES = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "PUBLIC_SUPABASE_ANON_KEY")


@dataclass(frozen=True)
class Credenciales:
    url: str
    servicio: str
    anon: str


@dataclass(frozen=True)
class Usuario:
    """Datos planos, sin nada atado a un event loop: se comparten entre tests."""

    id: str
    email: str
    token: str


# ── Clientes ─────────────────────────────────────────────────────────────────


def cliente_rest(cred: Credenciales, token: str | None = None) -> httpx.AsyncClient:
    """PostgREST con la anon key; con `token` va como ese usuario, igual que el navegador."""
    return httpx.AsyncClient(
        base_url=f"{cred.url}/rest/v1",
        headers={
            "apikey": cred.anon,
            "Authorization": f"Bearer {token or cred.anon}",
            "Content-Type": "application/json",
        },
        timeout=_TIMEOUT,
    )


def cliente_servicio(cred: Credenciales) -> httpx.AsyncClient:
    """Service key: bypassa RLS. Solo para verificar lo que quedó en la fila y limpiar."""
    return httpx.AsyncClient(
        base_url=f"{cred.url}/rest/v1",
        headers={
            "apikey": cred.servicio,
            "Authorization": f"Bearer {cred.servicio}",
            "Content-Type": "application/json",
        },
        timeout=_TIMEOUT,
    )


def cliente_admin(cred: Credenciales) -> httpx.AsyncClient:
    """API de administración de GoTrue, para crear y borrar los usuarios de prueba."""
    return httpx.AsyncClient(
        base_url=f"{cred.url}/auth/v1",
        headers={"apikey": cred.servicio, "Authorization": f"Bearer {cred.servicio}"},
        timeout=_TIMEOUT,
    )


# ── Alta y baja de usuarios desechables ──────────────────────────────────────


async def reintentar(operacion, intentos: int = 5):
    """Repite una llamada que la API de administración rechaza de vez en cuando.

    El proyecto está a medio camino entre las claves viejas y las nuevas —la
    service key ya es `sb_secret_…` y la anon key sigue siendo un JWT— y en ese
    estado GoTrue responde `bad_jwt` a peticiones perfectamente válidas, sin
    patrón. Reintentar convierte ese ruido en algo fiable; sin esto, un DELETE
    que se cae deja un usuario de prueba vivo en producción.
    """
    for intento in range(intentos):
        respuesta = await operacion()
        if respuesta.status_code < 400:
            return respuesta
        # Un 4xx que no sea de los intermitentes es una respuesta de verdad:
        # devolverla enseguida en vez de insistir contra una pared.
        if respuesta.status_code < 500 and respuesta.status_code not in (403, 408, 429):
            return respuesta
        await asyncio.sleep(0.4 * (intento + 1))
    return respuesta


async def _alta(cred: Credenciales, completar_perfil: bool = True) -> Usuario:
    """Crea un usuario confirmado y devuelve su sesión.

    `email_confirm` evita el correo de verificación: el endpoint de la web exige
    el email confirmado y aquí no hay bandeja de entrada que mirar.
    """
    email = f"{PREFIJO_EMAIL}{uuid4().hex}@example.com"

    async with cliente_admin(cred) as admin:
        alta = await reintentar(
            lambda: admin.post(
                "/admin/users",
                json={"email": email, "password": _CLAVE, "email_confirm": True},
            )
        )
        if alta.status_code >= 400:
            pytest.skip(f"no se pudo crear el usuario de prueba: {alta.status_code} {alta.text[:200]}")
        uid = alta.json()["id"]

        # El login por contraseña puede estar deshabilitado en el proyecto (el
        # .env trae credenciales de Google). Se salta con el motivo a la vista en
        # vez de dar un rojo que parecería un fallo del código.
        sesion = await reintentar(
            lambda: admin.post(
                "/token",
                params={"grant_type": "password"},
                json={"email": email, "password": _CLAVE},
                headers={"apikey": cred.anon, "Authorization": f"Bearer {cred.anon}"},
            )
        )
        if sesion.status_code >= 400:
            await reintentar(lambda: admin.delete(f"/admin/users/{uid}"), intentos=6)
            pytest.skip(f"login por contraseña no disponible: {sesion.status_code} {sesion.text[:200]}")

    usuario = Usuario(id=uid, email=email, token=sesion.json()["access_token"])

    if completar_perfil:
        # El trigger `crear_perfil_al_registrarse` deja el perfil vacío, y sin
        # nombre ni teléfono la web no deja publicar (`perfilCompleto`).
        async with cliente_rest(cred, usuario.token) as api:
            perfil = await api.patch(
                "/perfiles",
                params={"id": f"eq.{usuario.id}"},
                json={"nombre": "Usuario de prueba", "telefono": "+56 9 1111 1111"},
                headers=PREFER,
            )
            if perfil.status_code >= 400 or not perfil.json():
                await _baja(cred, usuario.id)
                pytest.fail(f"no se pudo completar el perfil: {perfil.status_code} {perfil.text[:200]}")

    return usuario


async def _baja(cred: Credenciales, uid: str) -> None:
    """Borra el usuario y, por si el CASCADE fallara, sus avisos primero."""
    async with cliente_servicio(cred) as servicio:
        await servicio.delete("/particulares_listings", params={"usuario_id": f"eq.{uid}"})
    async with cliente_admin(cred) as admin:
        await reintentar(lambda: admin.delete(f"/admin/users/{uid}"), intentos=6)


async def _barrer(cred: Credenciales) -> None:
    """Restos de corridas anteriores: avisos por prefijo y usuarios por email."""
    async with cliente_servicio(cred) as servicio:
        await servicio.delete(
            "/particulares_listings", params={"id_externo": f"like.{PREFIJO_EXTERNO}*"}
        )
    async with cliente_admin(cred) as admin:
        listado = await reintentar(lambda: admin.get("/admin/users", params={"per_page": 200}))
        if listado.status_code >= 400:
            return
        for usuario in listado.json().get("users", []):
            if str(usuario.get("email", "")).startswith(PREFIJO_EMAIL):
                await reintentar(lambda: admin.delete(f"/admin/users/{usuario['id']}"), intentos=6)


async def _restos(cred: Credenciales) -> list[str]:
    """Lo que la suite prometió no dejar. Si devuelve algo, la limpieza falló."""
    sobras: list[str] = []

    async with cliente_servicio(cred) as servicio:
        avisos = await servicio.get(
            "/particulares_listings",
            params={"id_externo": f"like.{PREFIJO_EXTERNO}*", "select": "id_externo"},
        )
        if avisos.status_code != 200:
            sobras.append(f"no se pudo revisar los avisos ({avisos.status_code})")
        else:
            sobras += [fila["id_externo"] for fila in avisos.json()]

    async with cliente_admin(cred) as admin:
        listado = await reintentar(lambda: admin.get("/admin/users", params={"per_page": 200}))
        if listado.status_code != 200:
            sobras.append(f"no se pudo revisar los usuarios ({listado.status_code})")
        else:
            sobras += [
                str(u.get("email"))
                for u in listado.json().get("users", [])
                if str(u.get("email", "")).startswith(PREFIJO_EMAIL)
            ]

    return sobras


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def credenciales(pytestconfig) -> Credenciales:
    if not (pytestconfig.getoption("--supabase") or os.getenv(_OPT_IN)):
        pytest.skip(f"requiere --supabase (o {_OPT_IN}=1): escribe en el Supabase real")
    faltan = [v for v in _VARIABLES if not os.getenv(v)]
    if faltan:
        pytest.skip(f"faltan variables: {', '.join(faltan)}")
    return Credenciales(
        url=os.environ["SUPABASE_URL"].rstrip("/"),
        servicio=os.environ["SUPABASE_SERVICE_KEY"].strip(),
        anon=os.environ["PUBLIC_SUPABASE_ANON_KEY"].strip(),
    )


@pytest.fixture(scope="session", autouse=True)
def barrido(credenciales: Credenciales):
    """Deja la mesa limpia antes y después, aunque la corrida anterior se cortara.

    Al final no basta con borrar: se comprueba. Esto escribe en producción, así
    que un resto que sobreviva tiene que salir en rojo y con nombre, no pasar
    desapercibido entre tests verdes.
    """
    asyncio.run(_barrer(credenciales))
    yield
    asyncio.run(_barrer(credenciales))
    sobras = asyncio.run(_restos(credenciales))
    if sobras:
        raise RuntimeError(f"la limpieza dejó restos en producción: {sobras}")


# Los usuarios se crean una vez por módulo y con `asyncio.run` a propósito: así no
# queda ningún objeto atado al event loop de un test, que pytest-asyncio cierra
# al terminar cada uno. Los clientes HTTP, que sí lo están, son por test.
@pytest.fixture(scope="module")
def usuario(credenciales: Credenciales):
    creado = asyncio.run(_alta(credenciales))
    try:
        yield creado
    finally:
        asyncio.run(_baja(credenciales, creado.id))


@pytest.fixture(scope="module")
def otro_usuario(credenciales: Credenciales):
    """Segundo usuario: sin alguien contra quien intentar el abuso, RLS no se prueba."""
    creado = asyncio.run(_alta(credenciales))
    try:
        yield creado
    finally:
        asyncio.run(_baja(credenciales, creado.id))


@pytest.fixture
def usuario_efimero(credenciales: Credenciales):
    """Usuario recién nacido, con el perfil como lo dejó el trigger: vacío."""
    creado = asyncio.run(_alta(credenciales, completar_perfil=False))
    try:
        yield creado
    finally:
        asyncio.run(_baja(credenciales, creado.id))


@pytest_asyncio.fixture
async def api(credenciales: Credenciales, usuario: Usuario):
    async with cliente_rest(credenciales, usuario.token) as cliente:
        yield cliente


@pytest_asyncio.fixture
async def api_otro(credenciales: Credenciales, otro_usuario: Usuario):
    async with cliente_rest(credenciales, otro_usuario.token) as cliente:
        yield cliente


@pytest_asyncio.fixture
async def anonimo(credenciales: Credenciales):
    """Lo que ve un visitante sin sesión."""
    async with cliente_rest(credenciales) as cliente:
        yield cliente


@pytest_asyncio.fixture
async def servicio(credenciales: Credenciales):
    async with cliente_servicio(credenciales) as cliente:
        yield cliente


@pytest_asyncio.fixture
async def admin(credenciales: Credenciales):
    async with cliente_admin(credenciales) as cliente:
        yield cliente


@pytest.fixture
def payload(usuario: Usuario):
    """Aviso válido mínimo, etiquetado y pausado.

    Pausado por defecto para que los avisos de prueba no lleguen a verse en el
    sitio público; los tests que necesitan el estado por defecto omiten la clave.
    """

    def _payload(**cambios) -> dict:
        base = {
            "id_externo": f"{PREFIJO_EXTERNO}{uuid4().hex}",
            "url": "https://carflip.cl/auto/p/test-pytest",
            "titulo": f"{ETIQUETA} Toyota Yaris Sport 2020",
            "usuario_id": usuario.id,
            "marca": "Toyota",
            "modelo": "Yaris",
            "version": "Sport",
            "anio": 2020,
            "km": 45000,
            "precio": 9500000,
            "ubicacion": "Ñuñoa, Metropolitana",
            "combustible": "Bencina",
            "transmision": "Manual",
            "estado": "pausado",
        }
        base.update(cambios)
        return base

    return _payload
