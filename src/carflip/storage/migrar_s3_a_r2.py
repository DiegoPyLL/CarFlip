"""
Migración de imágenes desde S3 → Cloudflare R2.

Flujo:
  1. Listar objetos en el bucket S3 de origen (prefijo configurable)
  2. Por cada objeto: descargar desde S3 en memoria
  3. Subir a R2 con la misma clave (o prefijo destino distinto)
  4. Verificar existencia en R2 tras la subida
  5. Reintentar hasta _MAX_REINTENTOS (x5, ventana de 2 horas)

Variables de entorno requeridas (.env):
  S3_BUCKET             — nombre del bucket S3 origen
  S3_PREFIX             — prefijo a filtrar (ej. "autocosmos/fotos/"), default ""
  S3_ACCESS_KEY_ID      — credencial S3
  S3_SECRET_ACCESS_KEY  — credencial S3
  S3_REGION             — región S3 (ej. "us-east-1")
  R2_ACCOUNT_ID         — Account ID de Cloudflare
  R2_BUCKET             — nombre del bucket R2 destino
  R2_ACCESS_KEY_ID      — token R2 (R2 API Token con permisos de escritura)
  R2_SECRET_ACCESS_KEY  — secret R2
  R2_PREFIX             — prefijo destino en R2, default igual que S3_PREFIX
"""

import asyncio
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parents[4]))

import aioboto3
from botocore.exceptions import ClientError
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

_MAX_REINTENTOS = 5
_INTERVALO_REINTENTOS_SEG = 1440  # 5 reintentos × 24 min ≈ 2 horas


# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────


class ConfigMigracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    s3_bucket: str
    s3_prefix: str = ""
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_region: str = "us-east-2"

    r2_account_id: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_prefix: str = ""  # si vacío, usa el mismo prefijo que S3


# ─── HELPERS DE CLIENTE ──────────────────────────────────────────────────────


def _endpoint_r2(account_id: str) -> str:
    return f"https://{account_id}.r2.cloudflarestorage.com"


def _sesion_s3(cfg: ConfigMigracion) -> aioboto3.Session:
    return aioboto3.Session(
        aws_access_key_id=cfg.s3_access_key_id,
        aws_secret_access_key=cfg.s3_secret_access_key,
        region_name=cfg.s3_region,
    )


def _sesion_r2(cfg: ConfigMigracion) -> aioboto3.Session:
    # R2 es compatible con la API S3 — solo cambia el endpoint
    return aioboto3.Session(
        aws_access_key_id=cfg.r2_access_key_id,
        aws_secret_access_key=cfg.r2_secret_access_key,
    )


# ─── OPERACIONES ATÓMICAS ────────────────────────────────────────────────────


async def _listar_claves_s3(cliente_s3, bucket: str, prefijo: str) -> list[str]:
    """Retorna todas las claves del bucket S3 bajo `prefijo`."""
    claves: list[str] = []
    paginator = cliente_s3.get_paginator("list_objects_v2")
    async for pagina in paginator.paginate(Bucket=bucket, Prefix=prefijo):
        for obj in pagina.get("Contents", []):
            claves.append(obj["Key"])
    logger.info(f"[s3→r2] {len(claves)} objetos encontrados en s3://{bucket}/{prefijo}")
    return claves


async def _descargar_s3(cliente_s3, bucket: str, clave: str) -> bytes | None:
    """Descarga un objeto de S3 y retorna sus bytes. None si falla."""
    try:
        respuesta = await cliente_s3.get_object(Bucket=bucket, Key=clave)
        async with respuesta["Body"] as stream:
            datos = await stream.read()
        logger.debug(f"[s3→r2] Descargado s3://{bucket}/{clave} ({len(datos):,} bytes)")
        return datos
    except ClientError as exc:
        logger.error(f"[s3→r2] Error al descargar s3://{bucket}/{clave}: {exc}")
        return None


async def _existe_en_r2(cliente_r2, bucket: str, clave: str) -> bool:
    """Verifica si un objeto ya existe en R2."""
    try:
        await cliente_r2.head_object(Bucket=bucket, Key=clave)
        return True
    except ClientError:
        return False


async def _subir_a_r2(cliente_r2, bucket: str, clave: str, datos: bytes) -> bool:
    """Sube `datos` a R2 bajo `clave` y verifica existencia. Retorna True si éxito."""
    try:
        await cliente_r2.put_object(Bucket=bucket, Key=clave, Body=datos)
        logger.debug(f"[s3→r2] Subido r2://{bucket}/{clave} ({len(datos):,} bytes)")
    except ClientError as exc:
        logger.error(f"[s3→r2] Error al subir r2://{bucket}/{clave}: {exc}")
        return False

    if not await _existe_en_r2(cliente_r2, bucket, clave):
        logger.error(f"[s3→r2] Verificación fallida — objeto no encontrado en R2: {clave}")
        return False

    return True


# ─── MIGRACIÓN CON RETRY ─────────────────────────────────────────────────────


async def _migrar_objeto(
    cliente_s3,
    cliente_r2,
    cfg: ConfigMigracion,
    clave_s3: str,
) -> bool:
    """
    Descarga un objeto de S3 y lo sube a R2.
    Reintenta hasta _MAX_REINTENTOS con backoff fijo.
    """
    prefijo_destino = cfg.r2_prefix if cfg.r2_prefix else cfg.s3_prefix
    # Reemplaza el prefijo origen por el destino en la clave
    if cfg.s3_prefix and clave_s3.startswith(cfg.s3_prefix):
        clave_r2 = prefijo_destino + clave_s3[len(cfg.s3_prefix):]
    else:
        clave_r2 = prefijo_destino + clave_s3

    for intento in range(1, _MAX_REINTENTOS + 1):
        datos = await _descargar_s3(cliente_s3, cfg.s3_bucket, clave_s3)
        if datos is None:
            logger.warning(
                f"[s3→r2] Descarga fallida intento {intento}/{_MAX_REINTENTOS}: {clave_s3}"
            )
        elif await _subir_a_r2(cliente_r2, cfg.r2_bucket, clave_r2, datos):
            return True
        else:
            logger.warning(
                f"[s3→r2] Subida fallida intento {intento}/{_MAX_REINTENTOS}: {clave_r2}"
            )

        if intento < _MAX_REINTENTOS:
            logger.warning(
                f"[s3→r2] Reintentando en {_INTERVALO_REINTENTOS_SEG // 60} min "
                f"(intento {intento}/{_MAX_REINTENTOS})"
            )
            await asyncio.sleep(_INTERVALO_REINTENTOS_SEG)

    logger.error(f"[s3→r2] Agotados {_MAX_REINTENTOS} reintentos: {clave_s3} → {clave_r2}")
    return False


# ─── ENTRYPOINT PRINCIPAL ────────────────────────────────────────────────────


async def migrar(cfg: ConfigMigracion) -> dict[str, int]:
    """
    Migra todos los objetos del prefijo S3 al bucket R2.
    Retorna conteo: {"ok": N, "fallidos": M}.
    """
    sesion_s3 = _sesion_s3(cfg)
    sesion_r2 = _sesion_r2(cfg)

    endpoint_r2 = _endpoint_r2(cfg.r2_account_id)
    logger.info(f"[s3→r2] Inicio migración s3://{cfg.s3_bucket} → r2://{cfg.r2_bucket}")
    logger.info(f"[s3→r2] Endpoint R2: {endpoint_r2}")

    async with sesion_s3.client("s3") as cliente_s3, sesion_r2.client(
        "s3", endpoint_url=endpoint_r2
    ) as cliente_r2:
        claves = await _listar_claves_s3(cliente_s3, cfg.s3_bucket, cfg.s3_prefix)

        ok = 0
        fallidos = 0
        for clave in claves:
            exito = await _migrar_objeto(cliente_s3, cliente_r2, cfg, clave)
            if exito:
                ok += 1
            else:
                fallidos += 1

    logger.info(f"[s3→r2] Migración finalizada — {ok} ok, {fallidos} fallidos de {len(claves)} total")
    return {"ok": ok, "fallidos": fallidos}


if __name__ == "__main__":
    cfg = ConfigMigracion()
    resultado = asyncio.run(migrar(cfg))
    if resultado["fallidos"]:
        sys.exit(1)
