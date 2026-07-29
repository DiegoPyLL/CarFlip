"""Subida de fotos de un aviso, contra el Supabase real: bucket y tabla a la vez.

Replica lo que hace `web/src/pages/api/publicacion/[id]/fotos.ts` paso a paso —
subir el archivo a `avisos-particulares`, insertar la fila en
`particulares_fotos` con la URL pública y por último sincronizar la portada del
aviso— pero por el mismo camino que un usuario real: la anon key más su JWT, sin
mocks ni service key salvo para releer y limpiar. Usa las fotos de
`imagenes subida publicaciones/`, que son las que trae el repo para esto.

Como en `test_creacion_aviso.py`, cada objeto que sube queda bajo
`<usuario_id>/<aviso_id>/…`, así que se borra a mano al terminar: el `CASCADE`
de Postgres se lleva la fila de `particulares_fotos` cuando se borra el usuario
de prueba, pero no se entera de Storage y el objeto quedaría huérfano.

Ejecutar con:

    pytest -m integration -v tests/publicaciones/test_subida_fotos.py --supabase
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from .conftest import PREFER

pytestmark = pytest.mark.integration

CARPETA_IMAGENES = Path(__file__).parent / "imagenes subida publicaciones"
BUCKET = "avisos-particulares"
TABLA_AVISOS = "/particulares_listings"
TABLA_FOTOS = "/particulares_fotos"


def imagenes() -> list[Path]:
    return sorted(CARPETA_IMAGENES.glob("*.jpg"))


# ── Clientes y aviso de apoyo ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def storage(credenciales, usuario):
    """Storage API con el JWT del usuario: mismo camino que sube el navegador."""
    async with httpx.AsyncClient(
        base_url=f"{credenciales.url}/storage/v1",
        headers={"apikey": credenciales.anon, "Authorization": f"Bearer {usuario.token}"},
        timeout=30,
    ) as cliente:
        yield cliente


@pytest_asyncio.fixture
async def storage_otro(credenciales, otro_usuario):
    async with httpx.AsyncClient(
        base_url=f"{credenciales.url}/storage/v1",
        headers={"apikey": credenciales.anon, "Authorization": f"Bearer {otro_usuario.token}"},
        timeout=30,
    ) as cliente:
        yield cliente


async def limpiar_carpeta(storage_cliente: httpx.AsyncClient, prefijo: str) -> None:
    """Borra todo lo que quedó bajo `<usuario_id>/<aviso_id>/` en el bucket."""
    listado = await storage_cliente.post(f"/object/list/{BUCKET}", json={"prefix": prefijo})
    if listado.status_code != 200:
        return
    rutas = [f"{prefijo}/{objeto['name']}" for objeto in listado.json()]
    if rutas:
        await storage_cliente.post(f"/object/remove/{BUCKET}", json={"prefixes": rutas})


@pytest_asyncio.fixture
async def aviso(api, storage, payload):
    """Un aviso real, propio del usuario de prueba, listo para colgarle fotos."""
    respuesta = await api.post(TABLA_AVISOS, json=payload(), headers=PREFER)
    assert respuesta.status_code == 201, respuesta.text[:300]
    fila = respuesta.json()[0]
    try:
        yield fila
    finally:
        await limpiar_carpeta(storage, f"{fila['usuario_id']}/{fila['id']}")


# ── El camino feliz: subir, registrar, sincronizar ───────────────────────────


async def test_sube_las_fotos_reales_del_disco_y_quedan_accesibles(
    api, servicio, storage, aviso, credenciales
):
    """Cada foto pasa por Storage y por la tabla, igual que hace la web."""
    fotos = imagenes()
    assert fotos, f"no hay imágenes de prueba en {CARPETA_IMAGENES}"

    filas_creadas = []
    for orden, ruta in enumerate(fotos):
        destino = f"{aviso['usuario_id']}/{aviso['id']}/{ruta.name.strip()}"

        subida = await storage.post(
            f"/object/{BUCKET}/{destino}",
            content=ruta.read_bytes(),
            headers={"Content-Type": "image/jpeg"},
        )
        assert subida.status_code in (200, 201), subida.text[:200]

        url_publica = f"{credenciales.url}/storage/v1/object/public/{BUCKET}/{destino}"
        fila_foto = await api.post(
            TABLA_FOTOS,
            json={"aviso_id": aviso["id"], "url": url_publica, "ruta": destino, "orden": orden},
            headers=PREFER,
        )
        assert fila_foto.status_code == 201, fila_foto.text[:200]
        filas_creadas.append(fila_foto.json()[0])

    guardadas = await servicio.get(
        TABLA_FOTOS,
        params={"aviso_id": f"eq.{aviso['id']}", "select": "*", "order": "orden.asc"},
    )
    assert guardadas.status_code == 200
    assert len(guardadas.json()) == len(fotos)
    assert [f["ruta"] for f in guardadas.json()] == [f["ruta"] for f in filas_creadas]

    # `sincronizarPortada`: la primera foto por orden pasa a ser `url_imagen`.
    portada = filas_creadas[0]["url"]
    sincronizado = await api.patch(
        TABLA_AVISOS,
        params={"id": f"eq.{aviso['id']}"},
        json={"url_imagen": portada},
        headers=PREFER,
    )
    assert sincronizado.status_code == 200, sincronizado.text[:200]
    releido = await servicio.get(TABLA_AVISOS, params={"id": f"eq.{aviso['id']}", "select": "url_imagen"})
    assert releido.json()[0]["url_imagen"] == portada

    # El bucket es público: la URL que quedó guardada sirve el mismo archivo.
    async with httpx.AsyncClient() as publico:
        respuesta = await publico.get(portada)
    assert respuesta.status_code == 200
    assert respuesta.content == fotos[0].read_bytes()


# ── Autorización: la misma RLS de los avisos, aplicada a las fotos ───────────


async def test_nadie_sube_una_foto_a_la_carpeta_de_otro(storage_otro, aviso):
    """La política de Storage compara el primer segmento de la ruta con `auth.uid()`."""
    destino = f"{aviso['usuario_id']}/{aviso['id']}/intruso.jpg"

    respuesta = await storage_otro.post(
        f"/object/{BUCKET}/{destino}",
        content=imagenes()[0].read_bytes(),
        headers={"Content-Type": "image/jpeg"},
    )

    assert respuesta.status_code in (400, 401, 403), respuesta.text[:200]


async def test_nadie_registra_una_fila_de_foto_en_el_aviso_de_otro(api_otro, aviso):
    """`fotos_escribe_dueno` exige que el aviso sea del dueño de la fila."""
    respuesta = await api_otro.post(
        TABLA_FOTOS,
        json={"aviso_id": aviso["id"], "url": "https://example.com/x.jpg", "ruta": "x/x.jpg", "orden": 0},
        headers=PREFER,
    )

    assert respuesta.status_code in (401, 403), respuesta.text[:200]
