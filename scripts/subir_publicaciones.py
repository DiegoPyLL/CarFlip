"""Publica avisos reales en CarFlip usando las fotos de disco.

Reparte las imágenes de `tests/publicaciones/imagenes subida publicaciones/`
entre varios autos de ejemplo y publica cada uno por el mismo camino que un
usuario real: login con email y contraseña, POST a
`/rest/v1/particulares_listings` y subida de fotos al bucket
`avisos-particulares`, todo con la anon key y el JWT de la cuenta. La única
autorización es la RLS de Supabase, igual que en la web.

`titulo`, `url` y `disponible` no se envían: la base los deriva del resto de
columnas con el trigger `particulares_deriva_campos` (migración 0018) y
sobreescribe cualquier valor que llegue.

Requiere en el entorno (`.env` sirve):
    SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY

La cuenta que publica es `PUBLICADOR_EMAIL` / `PUBLICADOR_PASSWORD` más abajo:
una cuenta de prueba, no una real de un usuario del sitio.

Ejecutar con:
    uv run python scripts/subir_publicaciones.py

Pide confirmación por consola. Con `--si` publica sin preguntar (útil cuando se
ejecuta sin stdin, por ejemplo desde el botón "Run" del editor).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

load_dotenv()

CARPETA_IMAGENES = Path(__file__).parent.parent / "tests/publicaciones/imagenes subida publicaciones"

# Cuenta de prueba que publica los avisos. No es la cuenta de un usuario real.
PUBLICADOR_EMAIL = "jeffabesos@gmail.com"
PUBLICADOR_PASSWORD = "dfñsl8347"

BUCKET = "avisos-particulares"
TABLA_AVISOS = "/particulares_listings"
TABLA_FOTOS = "/particulares_fotos"
PREFER = {"Prefer": "return=representation"}

# Autos de ejemplo: sólo columnas que `authenticated` puede escribir
# (GRANT por columna de la migración 0018). Cada uno se lleva un tramo de fotos.
AUTOS = [
    {
        "marca": "Toyota", "modelo": "Yaris", "version": "XLS", "anio": 2021,
        "km": 32000, "precio": 10500000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Ñuñoa, Metropolitana",
        "descripcion": "Yaris XLS único dueño, mantenciones al día, sin choques.",
    },
    {
        "marca": "Chevrolet", "modelo": "Sail", "version": "LT", "anio": 2019,
        "km": 58000, "precio": 6900000, "combustible": "Bencina", "transmision": "Manual",
        "traccion": "Delantera", "ubicacion": "San Bernardo, Metropolitana",
        "descripcion": "Sail LT económico, ideal primer auto, papeles al día.",
    },
    {
        "marca": "Nissan", "modelo": "Versa", "version": "Advance", "anio": 2020,
        "km": 41000, "precio": 8900000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Viña del Mar, Valparaíso",
        "descripcion": "Versa Advance full equipo, aire acondicionado, cámara de retroceso.",
    },
    {
        "marca": "Hyundai", "modelo": "Accent", "version": "GL", "anio": 2018,
        "km": 67000, "precio": 6200000, "combustible": "Bencina", "transmision": "Manual",
        "traccion": "Delantera", "ubicacion": "Concepción, Biobío",
        "descripcion": "Accent GL, mantención en agencia, cinturones y frenos nuevos.",
    },
    {
        "marca": "Suzuki", "modelo": "Swift", "version": "GLX", "anio": 2022,
        "km": 15000, "precio": 11800000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "La Serena, Coquimbo",
        "descripcion": "Swift GLX seminuevo, bajo kilometraje, aún en garantía de fábrica.",
    },
]

def confirmar() -> None:
    """Exige un 'si' por consola, salvo que se pase `--si` al ejecutar."""
    if "--si" in sys.argv:
        return
    try:
        respuesta = input("Escribe 'si' para continuar: ")
    except EOFError:
        sys.exit("No hay consola interactiva: vuelve a ejecutarlo con --si para confirmar.")
    if respuesta.strip().lower() != "si":
        sys.exit("Cancelado.")


def repartir(items: list, en_partes: int) -> list[list]:
    """Reparte `items` en `en_partes` tramos lo más parejos posible."""
    base, resto = divmod(len(items), en_partes)
    partes, inicio = [], 0
    for i in range(en_partes):
        fin = inicio + base + (1 if i < resto else 0)
        partes.append(items[inicio:fin])
        inicio = fin
    return partes


async def iniciar_sesion(cliente: httpx.AsyncClient, email: str, password: str) -> dict:
    respuesta = await cliente.post(
        "/auth/v1/token", params={"grant_type": "password"}, json={"email": email, "password": password}
    )
    if respuesta.status_code >= 400:
        sys.exit(f"No se pudo iniciar sesión como {email}: {respuesta.status_code} {respuesta.text[:300]}")
    return respuesta.json()


async def crear_aviso(cliente: httpx.AsyncClient, usuario_id: str, auto: dict) -> dict:
    cuerpo = {**auto, "id_externo": str(uuid4()), "usuario_id": usuario_id, "estado": "publicado"}
    respuesta = await cliente.post(TABLA_AVISOS, json=cuerpo, headers=PREFER)
    if respuesta.status_code != 201:
        sys.exit(f"No se pudo crear el aviso {auto['marca']} {auto['modelo']}: {respuesta.text[:300]}")
    return respuesta.json()[0]


async def subir_fotos(
    rest: httpx.AsyncClient, storage: httpx.AsyncClient, base_url: str, usuario_id: str, aviso: dict, fotos: list[Path]
) -> list[str]:
    urls = []
    for orden, ruta in enumerate(fotos):
        destino = f"{usuario_id}/{aviso['id']}/{ruta.name.strip()}"

        subida = await storage.post(
            f"/storage/v1/object/{BUCKET}/{destino}", content=ruta.read_bytes(), headers={"Content-Type": "image/jpeg"}
        )
        if subida.status_code not in (200, 201):
            print(f"  ! no se pudo subir {ruta.name.strip()}: {subida.text[:200]}")
            continue

        url_publica = f"{base_url}/storage/v1/object/public/{BUCKET}/{destino}"
        fila = await rest.post(
            TABLA_FOTOS,
            json={"aviso_id": aviso["id"], "url": url_publica, "ruta": destino, "orden": orden},
            headers=PREFER,
        )
        if fila.status_code != 201:
            print(f"  ! no se pudo registrar la foto {ruta.name.strip()}: {fila.text[:200]}")
            continue
        urls.append(url_publica)
    return urls


async def main() -> None:
    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    anon_key = os.environ["PUBLIC_SUPABASE_ANON_KEY"].strip()

    fotos = sorted(CARPETA_IMAGENES.glob("*.jpg"))
    if not fotos:
        sys.exit(f"No hay imágenes en {CARPETA_IMAGENES}")
    tramos = repartir(fotos, len(AUTOS))

    print(f"Se van a publicar {len(AUTOS)} avisos con {len(fotos)} fotos en total,")
    print(f"a nombre de {PUBLICADOR_EMAIL}, contra {base_url} (producción).")
    confirmar()

    async with httpx.AsyncClient(base_url=base_url, headers={"apikey": anon_key}, timeout=30) as auth:
        sesion = await iniciar_sesion(auth, PUBLICADOR_EMAIL, PUBLICADOR_PASSWORD)
    token = sesion["access_token"]
    usuario_id = sesion["user"]["id"]

    headers_rest = {"apikey": anon_key, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers_storage = {"apikey": anon_key, "Authorization": f"Bearer {token}"}

    async with (
        httpx.AsyncClient(base_url=f"{base_url}/rest/v1", headers=headers_rest, timeout=30) as rest,
        httpx.AsyncClient(base_url=base_url, headers=headers_storage, timeout=30) as storage,
    ):
        for auto, tramo in zip(AUTOS, tramos):
            aviso = await crear_aviso(rest, usuario_id, auto)
            print(f"Creado #{aviso['id']}: {auto['marca']} {auto['modelo']} {auto['version']} {auto['anio']}")

            urls = await subir_fotos(rest, storage, base_url, usuario_id, aviso, tramo)
            if urls:
                await rest.patch(TABLA_AVISOS, params={"id": f"eq.{aviso['id']}"}, json={"url_imagen": urls[0]}, headers=PREFER)
            print(f"  {len(urls)}/{len(tramo)} fotos subidas -> https://carflip.cl/auto/p/{aviso['id']}")


if __name__ == "__main__":
    asyncio.run(main())
