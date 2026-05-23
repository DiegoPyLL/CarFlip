"""Carga inicial de avisos desde S3 a Supabase.

Descarga todos los archivos */processed/avisos.jsonl del bucket S3,
normaliza url_imagen a CloudFront y hace upsert a las tablas de Supabase.

Uso:
    .venv\\Scripts\\python src/carflip/tools/cargar_desde_s3.py
"""

import asyncio
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parents[4]))

import aioboto3
from loguru import logger

from carflip.config import settings
from carflip.database.models import AutocosmosListing, YapoListing
from carflip.database.session import AsyncSessionLocal
from carflip.database.uploader import upsert_avisos
from carflip.scrapers.base import AvisoAuto

_MODELO_POR_FUENTE: dict[str, type] = {
    "autocosmos": AutocosmosListing,
    "yapo": YapoListing,
}

_PREFIJOS_S3 = ["autocosmos/", "yapo/"]
_SUFIJO_JSONL = "/processed/avisos.jsonl"
_TAMANO_LOTE = 200

_RE_S3_URL = re.compile(r"https?://[^/]*\.amazonaws\.com/(.+)")


def _normalizar_url_imagen(url: str | None) -> str | None:
    """Convierte URL de imagen a CloudFront. Soporta URL S3, clave relativa y URL CDN."""
    if not url:
        return None
    cdn = settings.cdn_base_url.strip().rstrip("/")
    if not cdn:
        return url
    if url.startswith(cdn):
        return url
    m = _RE_S3_URL.match(url)
    if m:
        return f"{cdn}/{m.group(1)}"
    if url.startswith(("autocosmos/", "yapo/", "mercadolibre/")):
        return f"{cdn}/{url}"
    return url


def _linea_a_aviso(data: dict) -> AvisoAuto | None:
    fuente = data.get("fuente", "")
    id_externo = data.get("id_externo", "")
    url = data.get("url", "")
    titulo = data.get("titulo", "")
    if not all([fuente, id_externo, url, titulo]):
        return None

    precio_raw = data.get("precio")
    precio = Decimal(str(precio_raw)) if precio_raw is not None else None

    return AvisoAuto(
        fuente=fuente,
        id_externo=id_externo,
        url=url,
        titulo=titulo,
        precio=precio,
        moneda=data.get("moneda", "CLP"),
        marca=data.get("marca"),
        modelo=data.get("modelo"),
        anio=data.get("anio"),
        km=data.get("km"),
        ubicacion=data.get("ubicacion"),
        combustible=data.get("combustible"),
        descripcion=data.get("descripcion"),
        url_imagen=_normalizar_url_imagen(data.get("url_imagen")),
        disponible=data.get("disponible"),
        fecha_publicacion=data.get("fecha_publicacion"),
    )


async def _listar_claves_jsonl(cliente) -> list[str]:
    claves: list[str] = []
    for prefijo in _PREFIJOS_S3:
        paginator = cliente.get_paginator("list_objects_v2")
        async for pagina in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefijo):
            for obj in pagina.get("Contents", []):
                if obj["Key"].endswith(_SUFIJO_JSONL):
                    claves.append(obj["Key"])
    return claves


async def _descargar_y_parsear(cliente, clave: str) -> list[AvisoAuto]:
    respuesta = await cliente.get_object(Bucket=settings.s3_bucket, Key=clave)
    contenido = await respuesta["Body"].read()
    avisos: list[AvisoAuto] = []
    for linea in contenido.decode("utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            data = json.loads(linea)
            aviso = _linea_a_aviso(data)
            if aviso:
                avisos.append(aviso)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(f"Línea inválida en {clave}: {exc}")
    return avisos


async def main() -> None:
    logger.info("Iniciando carga desde S3 → Supabase")

    sesion_s3 = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )

    avisos_por_fuente: dict[str, list[AvisoAuto]] = {f: [] for f in _MODELO_POR_FUENTE}
    archivos_ok = 0
    archivos_error = 0

    async with sesion_s3.client("s3") as cliente:  # type: ignore[attr-defined]
        claves = await _listar_claves_jsonl(cliente)
        logger.info(f"Archivos JSONL encontrados en S3: {len(claves)}")

        for clave in claves:
            try:
                avisos = await _descargar_y_parsear(cliente, clave)
                for aviso in avisos:
                    if aviso.fuente in avisos_por_fuente:
                        avisos_por_fuente[aviso.fuente].append(aviso)
                    else:
                        logger.warning(f"Fuente desconocida '{aviso.fuente}' en {clave}")
                archivos_ok += 1
                logger.debug(f"[{clave}] {len(avisos)} avisos parseados")
            except Exception as exc:
                archivos_error += 1
                logger.error(f"Error descargando {clave}: {exc}")

    total_cargados = 0
    async with AsyncSessionLocal() as sesion:
        for fuente, model_class in _MODELO_POR_FUENTE.items():
            avisos = avisos_por_fuente[fuente]
            if not avisos:
                logger.info(f"[{fuente}] Sin avisos — se omite")
                continue
            logger.info(f"[{fuente}] Cargando {len(avisos)} avisos en lotes de {_TAMANO_LOTE}...")
            for i in range(0, len(avisos), _TAMANO_LOTE):
                lote = avisos[i : i + _TAMANO_LOTE]
                n = await upsert_avisos(sesion, lote, model_class)
                total_cargados += n
                logger.info(f"[{fuente}] Lote {i // _TAMANO_LOTE + 1}: {n} filas upserted")

    logger.info(
        f"Carga completa — archivos: {archivos_ok} OK / {archivos_error} error"
        f" — avisos upserted: {total_cargados}"
    )


if __name__ == "__main__":
    asyncio.run(main())
