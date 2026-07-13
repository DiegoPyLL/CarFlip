"""Carga de run_reports desde S3 a Supabase (scrape_runs + run_fail_logs).

Descarga todos los archivos */logs/run_report.json del bucket S3, parsea las
métricas de cada corrida y las upsertea en scrape_runs; los FAIL LOGs se
reemplazan completos en run_fail_logs. Idempotente: la clave natural es
(source, started_at), re-ejecutar no duplica corridas.

Uso:
    .venv\\Scripts\\python src/carflip/tools/cargar_reports_s3.py
    .venv\\Scripts\\python src/carflip/tools/cargar_reports_s3.py --local "run_report_*.json"
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parents[4]))

import aioboto3
from loguru import logger
from sqlalchemy import delete, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.config import settings
from carflip.database.models import RunFailLog, ScrapedRun
from carflip.database.session import AsyncSessionLocal

_FUENTES = ["autocosmos", "yapo", "autosusados", "checkeados"]
_SUFIJO_REPORTE = "/logs/run_report.json"
_LOTE_FAIL_LOGS = 2000

_COLUMNAS_METRICAS = [
    "finished_at",
    "items_found",
    "errors",
    "duracion_segundos",
    "paginas_procesadas",
    "avisos_encontrados",
    "avisos_unicos",
    "avisos_validos",
    "avisos_rechazados",
]


def _parsear_fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha


def _reporte_a_fila(data: dict) -> tuple[dict, list[dict]] | None:
    """Convierte un run_report.json en (fila scrape_runs, filas run_fail_logs)."""
    fuente = data.get("fuente")
    started_at = _parsear_fecha(data.get("timestamp"))
    if not fuente or started_at is None:
        return None

    duracion = data.get("duracion_segundos")
    finished_at = (
        started_at + timedelta(seconds=float(duracion)) if duracion is not None else None
    )
    fail_logs_raw = data.get("fail_logs") or []

    fila_run = {
        "source": fuente,
        "started_at": started_at,
        "finished_at": finished_at,
        "items_found": data.get("avisos_encontrados") or 0,
        "errors": len(fail_logs_raw),
        "duracion_segundos": duracion,
        "paginas_procesadas": data.get("paginas_procesadas"),
        "avisos_encontrados": data.get("avisos_encontrados"),
        "avisos_unicos": data.get("avisos_unicos"),
        "avisos_validos": data.get("avisos_validos"),
        "avisos_rechazados": data.get("avisos_rechazados"),
    }

    filas_fails: list[dict] = []
    for fl in fail_logs_raw:
        if not isinstance(fl, dict) or not fl.get("etapa") or not fl.get("motivo"):
            logger.warning(f"[{fuente}] FAIL LOG malformado en reporte — omitido")
            continue
        filas_fails.append(
            {
                "fuente": fl.get("fuente") or fuente,
                "etapa": str(fl["etapa"])[:50],
                "motivo": str(fl["motivo"]),
                "id_externo": fl.get("id_externo"),
                "timestamp": _parsear_fecha(fl.get("timestamp")),
            }
        )
    return fila_run, filas_fails


async def _upsert_reporte(
    sesion: AsyncSession, fila_run: dict, filas_fails: list[dict]
) -> int:
    """Upsertea la corrida y reemplaza sus FAIL LOGs. Retorna el run_id."""
    tabla_runs = ScrapedRun.__table__
    tabla_fails = RunFailLog.__table__

    stmt = pg_insert(tabla_runs).values(fila_run)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_scrape_runs_source_started_at",
        set_={col: getattr(stmt.excluded, col) for col in _COLUMNAS_METRICAS},
    ).returning(tabla_runs.c.id)
    run_id = (await sesion.execute(stmt)).scalar_one()

    await sesion.execute(delete(tabla_fails).where(tabla_fails.c.run_id == run_id))
    for inicio in range(0, len(filas_fails), _LOTE_FAIL_LOGS):
        lote = [{**f, "run_id": run_id} for f in filas_fails[inicio : inicio + _LOTE_FAIL_LOGS]]
        await sesion.execute(insert(tabla_fails).values(lote))

    await sesion.commit()
    return run_id


async def _listar_claves_reportes(cliente) -> list[str]:
    claves: list[str] = []
    for fuente in _FUENTES:
        paginator = cliente.get_paginator("list_objects_v2")
        async for pagina in paginator.paginate(Bucket=settings.s3_bucket, Prefix=f"{fuente}/"):
            for obj in pagina.get("Contents", []):
                if obj["Key"].endswith(_SUFIJO_REPORTE):
                    claves.append(obj["Key"])
    return sorted(claves)


async def _cargar_reportes(reportes: list[tuple[str, dict]]) -> None:
    """Parsea y upsertea una lista de (origen, reporte_json) a Supabase."""
    cargados = 0
    omitidos = 0
    async with AsyncSessionLocal() as sesion:
        for origen, data in reportes:
            parseado = _reporte_a_fila(data)
            if parseado is None:
                omitidos += 1
                logger.warning(f"[{origen}] Reporte sin fuente o timestamp — omitido")
                continue
            fila_run, filas_fails = parseado
            run_id = await _upsert_reporte(sesion, fila_run, filas_fails)
            cargados += 1
            logger.info(
                f"[{fila_run['source']}] run {run_id} — {fila_run['started_at']:%Y-%m-%d %H:%M} — "
                f"{fila_run['avisos_validos']}/{fila_run['avisos_encontrados']} válidos, "
                f"{len(filas_fails)} FAIL LOGs ({origen})"
            )
    logger.info(f"Carga completa — {cargados} corridas upserted, {omitidos} omitidas")


async def _main_s3() -> None:
    logger.info("Cargando run_reports desde S3 → Supabase")
    sesion_s3 = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    reportes: list[tuple[str, dict]] = []
    async with sesion_s3.client("s3") as cliente:  # type: ignore[attr-defined]
        claves = await _listar_claves_reportes(cliente)
        logger.info(f"run_report.json encontrados en S3: {len(claves)}")
        for clave in claves:
            try:
                respuesta = await cliente.get_object(Bucket=settings.s3_bucket, Key=clave)
                contenido = await respuesta["Body"].read()
                reportes.append((f"s3://{clave}", json.loads(contenido)))
            except Exception as exc:
                logger.error(f"Error descargando {clave}: {exc}")
    await _cargar_reportes(reportes)


async def _main_local(patrones: list[str]) -> None:
    logger.info(f"Cargando run_reports locales → Supabase ({patrones})")
    reportes: list[tuple[str, dict]] = []
    for patron in patrones:
        rutas = sorted(Path.cwd().glob(patron)) if any(c in patron for c in "*?[") else [Path(patron)]
        for ruta in rutas:
            try:
                reportes.append((ruta.name, json.loads(ruta.read_text(encoding="utf-8"))))
            except Exception as exc:
                logger.error(f"Error leyendo {ruta}: {exc}")
    if not reportes:
        logger.warning("Ningún archivo local coincide con los patrones")
        return
    await _cargar_reportes(reportes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga run_reports (S3 o locales) a Supabase")
    parser.add_argument(
        "--local",
        nargs="+",
        metavar="PATRON",
        help="cargar archivos JSON locales (acepta globs) en vez de listar S3",
    )
    args = parser.parse_args()
    if args.local:
        asyncio.run(_main_local(args.local))
    else:
        asyncio.run(_main_s3())


if __name__ == "__main__":
    main()
