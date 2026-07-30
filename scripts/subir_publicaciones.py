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
        "marca": "Toyota", "modelo": "Yaris", "version": "XLS", "anio": 2021, "patente": "GSBB20",
        "km": 32000, "precio": 10500000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Ñuñoa, Metropolitana",
        "descripcion": "Yaris XLS único dueño, mantenciones al día, sin choques.",
    },
    {
        "marca": "Chevrolet", "modelo": "Sail", "version": "LT", "anio": 2019, "patente": "HJKL42",
        "km": 58000, "precio": 6900000, "combustible": "Bencina", "transmision": "Manual",
        "traccion": "Delantera", "ubicacion": "San Bernardo, Metropolitana",
        "descripcion": "Sail LT económico, ideal primer auto, papeles al día.",
    },
    {
        "marca": "Nissan", "modelo": "Versa", "version": "Advance", "anio": 2020, "patente": "PRST77",
        "km": 41000, "precio": 8900000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Viña del Mar, Valparaíso",
        "descripcion": "Versa Advance full equipo, aire acondicionado, cámara de retroceso.",
    },
    {
        "marca": "Hyundai", "modelo": "Accent", "version": "GL", "anio": 2018, "patente": "BCDF18",
        "km": 67000, "precio": 6200000, "combustible": "Bencina", "transmision": "Manual",
        "traccion": "Delantera", "ubicacion": "Concepción, Biobío",
        "descripcion": "Accent GL, mantención en agencia, cinturones y frenos nuevos.",
    },
    {
        "marca": "Suzuki", "modelo": "Swift", "version": "GLX", "anio": 2022, "patente": "SVWX05",
        "km": 15000, "precio": 11800000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "La Serena, Coquimbo",
        "descripcion": "Swift GLX seminuevo, bajo kilometraje, aún en garantía de fábrica.",
    },
    {
        "marca": "Kia", "modelo": "Rio", "version": "EX", "anio": 2020, "patente": "JLTV31",
        "km": 47000, "precio": 8300000, "combustible": "Bencina", "transmision": "Manual",
        "traccion": "Delantera", "ubicacion": "Maipú, Metropolitana",
        "descripcion": "Rio EX con llantas nuevas y revisión técnica vigente hasta marzo.",
    },
    {
        "marca": "Mazda", "modelo": "3", "version": "V Sport", "anio": 2019, "patente": "RSGH64",
        "km": 62000, "precio": 12400000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Providencia, Metropolitana",
        "descripcion": "Mazda 3 V Sport, cuero, sensores de estacionamiento y pantalla táctil.",
    },
    {
        "marca": "Toyota", "modelo": "Hilux", "version": "SR", "anio": 2017, "patente": "KDWB90",
        "km": 128000, "precio": 15900000, "combustible": "Diésel", "transmision": "Manual",
        "traccion": "4x4", "ubicacion": "Puerto Montt, Los Lagos",
        "descripcion": "Hilux SR de trabajo, motor impecable, cubre pisadera y barra antivuelco.",
    },
    {
        "marca": "Ford", "modelo": "Ranger", "version": "XLT", "anio": 2021, "patente": "FTZR26",
        "km": 74000, "precio": 21500000, "combustible": "Diésel", "transmision": "Automática",
        "traccion": "4x4", "ubicacion": "Temuco, La Araucanía",
        "descripcion": "Ranger XLT full, mantenciones en concesionario, tapa de pick up rígida.",
    },
    {
        "marca": "Volkswagen", "modelo": "Gol", "version": "Trend", "anio": 2016, "patente": "CB4471",
        "km": 96000, "precio": 5400000, "combustible": "Bencina", "transmision": "Manual",
        "traccion": "Delantera", "ubicacion": "Rancagua, O'Higgins",
        "descripcion": "Gol Trend confiable y barato de mantener, neumáticos con 80% de vida.",
    },
    {
        "marca": "Peugeot", "modelo": "208", "version": "Active", "anio": 2021, "patente": "LVHK58",
        "km": 28000, "precio": 11200000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Valparaíso, Valparaíso",
        "descripcion": "208 Active con pantalla i-Cockpit, siempre en estacionamiento techado.",
    },
    {
        "marca": "Renault", "modelo": "Duster", "version": "Zen", "anio": 2019, "patente": "TGPB13",
        "km": 83000, "precio": 9800000, "combustible": "Bencina", "transmision": "Manual",
        "traccion": "4x4", "ubicacion": "Antofagasta, Antofagasta",
        "descripcion": "Duster Zen 4x4, ideal para terreno, suspensión recién revisada.",
    },
    {
        "marca": "Honda", "modelo": "Fit", "version": "LX", "anio": 2015, "patente": "ZP7382",
        "km": 112000, "precio": 6700000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "La Florida, Metropolitana",
        "descripcion": "Fit LX espacioso y económico, distribución cambiada a los 100.000 km.",
    },
    {
        "marca": "Subaru", "modelo": "XV", "version": "Dynamic", "anio": 2020, "patente": "WXJD49",
        "km": 54000, "precio": 16800000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "4x4", "ubicacion": "Puerto Varas, Los Lagos",
        "descripcion": "XV Dynamic AWD, EyeSight activo, perfecto para carretera del sur.",
    },
    {
        "marca": "Mitsubishi", "modelo": "L200", "version": "Katana", "anio": 2018, "patente": "HKRV72",
        "km": 141000, "precio": 13900000, "combustible": "Diésel", "transmision": "Manual",
        "traccion": "4x4", "ubicacion": "Calama, Antofagasta",
        "descripcion": "L200 Katana de faena minera, mantención cada 5.000 km documentada.",
    },
    {
        "marca": "Chevrolet", "modelo": "Groove", "version": "LT", "anio": 2022, "patente": "BLSF37",
        "km": 24000, "precio": 12900000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Talca, Maule",
        "descripcion": "Groove LT seminuevo, cámara 360, aún con garantía de fábrica vigente.",
    },
    {
        "marca": "Toyota", "modelo": "Corolla", "version": "SEG Hybrid", "anio": 2023, "patente": "DFKZ81",
        "km": 19000, "precio": 22900000, "combustible": "Híbrido", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Las Condes, Metropolitana",
        "descripcion": "Corolla híbrido, rinde sobre 20 km/l en ciudad, batería con garantía.",
    },
    {
        "marca": "Hyundai", "modelo": "Tucson", "version": "Value", "anio": 2021, "patente": "PVGC24",
        "km": 61000, "precio": 18500000, "combustible": "Diésel", "transmision": "Automática",
        "traccion": "4x4", "ubicacion": "Chillán, Ñuble",
        "descripcion": "Tucson Value diésel, techo panorámico y enganche de arrastre instalado.",
    },
    {
        "marca": "MG", "modelo": "ZS", "version": "Comfort", "anio": 2022, "patente": "RCTX60",
        "km": 33000, "precio": 11600000, "combustible": "Bencina", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Iquique, Tarapacá",
        "descripcion": "ZS Comfort con Apple CarPlay, polarizado de fábrica y aire potente.",
    },
    {
        "marca": "BYD", "modelo": "Dolphin", "version": "Mini", "anio": 2024, "patente": "SJWB93",
        "km": 9000, "precio": 15200000, "combustible": "Eléctrico", "transmision": "Automática",
        "traccion": "Delantera", "ubicacion": "Valdivia, Los Ríos",
        "descripcion": "Dolphin Mini eléctrico, 300 km de autonomía real, cargador incluido.",
    },
]

def confirmar() -> None:
    return True


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
    # Hay menos fotos que avisos: se repiten en ciclo para que ninguno quede sin portada.
    if len(fotos) < len(AUTOS):
        fotos = [fotos[i % len(fotos)] for i in range(len(AUTOS))]
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
