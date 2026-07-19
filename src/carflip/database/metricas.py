"""Persistencia de métricas de cada corrida en scrape_runs + run_fail_logs.

El upsert es idempotente: la clave natural es (source, started_at), de modo que
re-ejecutar una corrida no duplica filas.
"""

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import delete, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.database.models import RunFailLog, ScrapedRun

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


def _parsear_fecha(valor: str | datetime | None) -> datetime | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        fecha = valor
    else:
        try:
            fecha = datetime.fromisoformat(valor)
        except ValueError:
            return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha


def _reporte_a_filas(reporte: dict) -> tuple[dict, list[dict]] | None:
    """Convierte un run_report en (fila scrape_runs, filas run_fail_logs)."""
    fuente = reporte.get("fuente")
    started_at = _parsear_fecha(reporte.get("timestamp"))
    if not fuente or started_at is None:
        return None

    duracion = reporte.get("duracion_segundos")
    finished_at = (
        started_at + timedelta(seconds=float(duracion)) if duracion is not None else None
    )
    fail_logs_raw = reporte.get("fail_logs") or []

    fila_run = {
        "source": fuente,
        "started_at": started_at,
        "finished_at": finished_at,
        "items_found": reporte.get("avisos_encontrados") or 0,
        "errors": len(fail_logs_raw),
        "duracion_segundos": duracion,
        "paginas_procesadas": reporte.get("paginas_procesadas"),
        "avisos_encontrados": reporte.get("avisos_encontrados"),
        "avisos_unicos": reporte.get("avisos_unicos"),
        "avisos_validos": reporte.get("avisos_validos"),
        "avisos_rechazados": reporte.get("avisos_rechazados"),
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


async def guardar_run_report(sesion: AsyncSession, reporte: dict) -> int | None:
    """Upsertea la corrida y reemplaza sus FAIL LOGs. Retorna el run_id."""
    parseado = _reporte_a_filas(reporte)
    if parseado is None:
        logger.warning("Reporte sin fuente o timestamp — no se guardan métricas")
        return None
    fila_run, filas_fails = parseado

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
    logger.info(
        f"[{fila_run['source']}] Métricas guardadas — run {run_id}, "
        f"{fila_run['avisos_validos']}/{fila_run['avisos_encontrados']} válidos, "
        f"{len(filas_fails)} FAIL LOGs"
    )
    return run_id
