"""Subida a S3 y URLs públicas vía CloudFront."""

import asyncio
from pathlib import Path

import aioboto3
from botocore.exceptions import ClientError
from loguru import logger

from carflip.config import settings

_S3_MAX_REINTENTOS = 12
_S3_INTERVALO_SEG = 600

_TIPOS_MIME: dict[str, str] = {
    ".avif": "image/avif",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
}


def content_type_desde_ruta(ruta: Path | str) -> str:
    sufijo = Path(ruta).suffix.lower()
    return _TIPOS_MIME.get(sufijo, "application/octet-stream")


def url_cdn_desde_clave_s3(clave_s3: str) -> str | None:
    """Arma URL CloudFront si CDN_BASE_URL está en .env."""
    base = settings.cdn_base_url.strip().rstrip("/")
    if not base:
        return None
    return f"{base}/{clave_s3.lstrip('/')}"


async def cargar_a_s3_con_retry(
    ruta_local: Path,
    clave_s3: str,
    *,
    etiqueta_log: str = "s3",
    skip_si_existe: bool = False,
) -> bool:
    """Sube archivo a S3 con Content-Type correcto y reintentos."""
    sesion = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    datos = ruta_local.read_bytes()
    content_type = content_type_desde_ruta(ruta_local)

    async with sesion.client("s3") as cliente:  # type: ignore[attr-defined]
        if skip_si_existe:
            try:
                await cliente.head_object(Bucket=settings.s3_bucket, Key=clave_s3)
                logger.debug(f"[{etiqueta_log}] S3 skip (ya existe): {clave_s3}")
                return True
            except ClientError:
                pass

        for intento in range(1, _S3_MAX_REINTENTOS + 1):
            try:
                await cliente.put_object(
                    Bucket=settings.s3_bucket,
                    Key=clave_s3,
                    Body=datos,
                    ContentType=content_type,
                )
                await cliente.head_object(Bucket=settings.s3_bucket, Key=clave_s3)
                logger.debug(f"[{etiqueta_log}] S3 upload OK: {clave_s3} ({content_type})")
                return True
            except (ClientError, Exception) as exc:
                if intento < _S3_MAX_REINTENTOS:
                    logger.warning(
                        f"[{etiqueta_log}] S3 upload fallido intento {intento}/{_S3_MAX_REINTENTOS}"
                        f" — {clave_s3}: {exc}. Reintentando en {_S3_INTERVALO_SEG // 60} min."
                    )
                    await asyncio.sleep(_S3_INTERVALO_SEG)
                else:
                    logger.error(
                        f"[{etiqueta_log}] S3 upload agotó {_S3_MAX_REINTENTOS} reintentos:"
                        f" {clave_s3} — {exc}"
                    )
    return False
