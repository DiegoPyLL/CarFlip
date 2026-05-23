"""
Utilidades de logging estructurado para los scrapers de CarFlip.

Provee:
- configurar_sinks_run()  → sinks loguru filtrados por fase/tipo en un directorio por run
- eliminar_sinks()        → limpia los sinks al terminar el run
- log_banner_fase()       → banner visual de inicio de fase en consola
- log_resumen_fase()      → línea de resumen al terminar una fase
"""

from datetime import datetime
from pathlib import Path

from loguru import logger

_FMT_ARCHIVO = "{time:HH:mm:ss} | {level: <7} | {message}"

_SINKS_SPEC: list[tuple[str, str | None, str | None]] = [
    # (nombre_archivo, campo_extra, valor_extra)
    ("todo.log",       None,    None),
    ("ingesta.log",    "fase",  "ingesta"),
    ("limpieza.log",   "fase",  "limpieza"),
    ("validacion.log", "fase",  "validacion"),
    ("fotos.log",      "tipo",  "fotos"),
    ("metadata.log",   "tipo",  "metadata"),
]


def configurar_sinks_run(fuente: str, carpeta_run: Path) -> list[int]:
    """
    Registra sinks loguru filtrados para un run específico.

    Crea 5 archivos bajo `carpeta_run/`:
      ingesta.log, limpieza.log, validacion.log, fotos.log, metadata.log

    Retorna la lista de IDs de sink para pasarlos a `eliminar_sinks()`.
    """
    carpeta_run.mkdir(parents=True, exist_ok=True)
    ids: list[int] = []

    for nombre, campo, valor in _SINKS_SPEC:
        def _filtro(record, campo=campo, valor=valor) -> bool:
            if campo is None:
                return True
            return record["extra"].get(campo) == valor

        sid = logger.add(
            carpeta_run / nombre,
            filter=_filtro,
            format=_FMT_ARCHIVO,
            level="DEBUG",
            encoding="utf-8",
        )
        ids.append(sid)

    logger.debug(f"[{fuente}] Sinks de run configurados en {carpeta_run}")
    return ids


def eliminar_sinks(sink_ids: list[int]) -> None:
    """Elimina los sinks registrados para un run."""
    for sid in sink_ids:
        try:
            logger.remove(sid)
        except ValueError:
            pass


def log_banner_fase(fuente: str, num: int, nombre: str) -> None:
    """Imprime un banner visual de inicio de fase."""
    linea = "═" * 50
    logger.info(f"{linea}")
    logger.info(f"[{fuente}] FASE {num}: {nombre}")
    logger.info(f"{linea}")


def log_resumen_fase(fuente: str, nombre: str, campos: dict[str, object]) -> None:
    """
    Imprime una línea de resumen al terminar una fase.

    Ejemplo:
        log_resumen_fase("autocosmos", "INGESTA", {
            "avisos": 45,
            "fotos_ok": "43/45",
            "json_ok": "45/45",
            "duracion": "45s",
        })
        → [autocosmos] ── RESUMEN INGESTA ── avisos: 45 | fotos_ok: 43/45 | ...
    """
    partes = " | ".join(f"{k}: {v}" for k, v in campos.items())
    logger.info(f"[{fuente}] ── RESUMEN {nombre} ── {partes}")


def carpeta_logs_run(fuente: str, ts: datetime | None = None) -> Path:
    """Retorna la ruta estándar del directorio de logs para un run."""
    fecha_str = (ts or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return Path("logs") / fuente / f"run_{fecha_str}"
