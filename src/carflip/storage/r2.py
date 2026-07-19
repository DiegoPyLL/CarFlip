"""Subida de objetos a Cloudflare R2 y URLs públicas vía CDN."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aioboto3
from botocore.exceptions import ClientError
from loguru import logger

from carflip.config import settings

_MAX_REINTENTOS = 12
_INTERVALO_SEG = 600

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


def url_publica(clave: str) -> str | None:
    """Arma la URL pública del objeto si CDN_BASE_URL está en .env."""
    base = settings.cdn_base_url.strip().rstrip("/")
    if not base:
        return None
    return f"{base}/{clave.lstrip('/')}"


@asynccontextmanager
async def cliente_objetos() -> AsyncIterator:
    """Context manager que abre un único cliente R2 compartible por toda una ejecución."""
    if not settings.r2_account_id:
        raise RuntimeError("R2_ACCOUNT_ID no está configurado — no se puede subir a R2")
    sesion = aioboto3.Session(
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
    )
    # R2 habla el protocolo S3 — solo cambia el endpoint.
    async with sesion.client(  # type: ignore[attr-defined]
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        region_name="auto",
    ) as cliente:
        yield cliente


@asynccontextmanager
async def cliente_objetos_opcional(activo: bool) -> AsyncIterator:
    """Igual que `cliente_objetos`, pero cede None si no se va a subir nada."""
    if not activo:
        yield None
        return
    async with cliente_objetos() as cliente:
        yield cliente


async def subir_objeto_con_retry(
    ruta_local: Path,
    clave: str,
    *,
    etiqueta_log: str = "r2",
    skip_si_existe: bool = False,
    cliente: object | None = None,
) -> bool:
    """Sube un archivo a R2 con Content-Type correcto y reintentos.

    Si se pasa `cliente` (obtenido de `async with cliente_objetos()`), se reutiliza
    la conexión existente — evita crear/destruir un cliente por cada archivo,
    lo que causaba ClientConnectionResetError en uploads concurrentes.
    """
    datos = ruta_local.read_bytes()
    content_type = content_type_desde_ruta(ruta_local)

    async def _subir(c: object) -> bool:
        if skip_si_existe:
            try:
                await c.head_object(Bucket=settings.r2_bucket, Key=clave)  # type: ignore[attr-defined]
                logger.debug(f"[{etiqueta_log}] R2 skip (ya existe): {clave}")
                return True
            except ClientError:
                pass

        for intento in range(1, _MAX_REINTENTOS + 1):
            try:
                await c.put_object(  # type: ignore[attr-defined]
                    Bucket=settings.r2_bucket,
                    Key=clave,
                    Body=datos,
                    ContentType=content_type,
                )
                await c.head_object(Bucket=settings.r2_bucket, Key=clave)  # type: ignore[attr-defined]
                logger.debug(f"[{etiqueta_log}] R2 upload OK: {clave} ({content_type})")
                return True
            except (ClientError, Exception) as exc:
                if intento < _MAX_REINTENTOS:
                    logger.warning(
                        f"[{etiqueta_log}] R2 upload fallido intento {intento}/{_MAX_REINTENTOS}"
                        f" — {clave}: {exc}. Reintentando en {_INTERVALO_SEG // 60} min."
                    )
                    await asyncio.sleep(_INTERVALO_SEG)
                else:
                    logger.error(
                        f"[{etiqueta_log}] R2 upload agotó {_MAX_REINTENTOS} reintentos:"
                        f" {clave} — {exc}"
                    )
        return False

    if cliente is not None:
        return await _subir(cliente)

    async with cliente_objetos() as c:
        return await _subir(c)
