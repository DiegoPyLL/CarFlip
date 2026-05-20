import asyncio
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from carflip.config import settings
from carflip.database.session import AsyncSessionLocal
from carflip.scrapers.AutoCosmos.autocosmosCloud import ScraperAutocosmosCloud
from carflip.scrapers.Yapo.yapoCloud import ScraperYapoCloud

# Orden de ejecución — un scraper a la vez para mantener recursos bajos.
# Para agregar un scraper nuevo: añadir una tupla (nombre, Clase) al final.
_SCRAPERS_ORDENADOS: list[tuple[str, type]] = [
    ("autocosmos", ScraperAutocosmosCloud),
    ("yapo", ScraperYapoCloud),
]

# Dict para lookups por nombre (usado por carflip run --scraper <nombre>)
_SCRAPERS: dict[str, type] = {nombre: cls for nombre, cls in _SCRAPERS_ORDENADOS}


async def run_scrapers(scraper_name: str = "all") -> None:
    """Ejecuta los scrapers de forma secuencial y sube los avisos a PostgreSQL."""
    if scraper_name == "all":
        a_ejecutar = _SCRAPERS_ORDENADOS
    elif scraper_name in _SCRAPERS:
        a_ejecutar = [(scraper_name, _SCRAPERS[scraper_name])]
    else:
        logger.error(f"[orquestrador] Scraper no encontrado: {scraper_name}")
        return

    total = len(a_ejecutar)
    logger.info(f"[orquestrador] Ciclo iniciado — {total} scraper(s) a ejecutar")
    inicio_ciclo = datetime.now()
    avisos_totales = 0

    async with AsyncSessionLocal() as session:
        for i, (nombre, scraper_cls) in enumerate(a_ejecutar, start=1):
            logger.info(f"[orquestrador] [{i}/{total}] Iniciando: {nombre}")
            inicio = datetime.now()

            scraper = scraper_cls()
            resultado = await scraper.ejecutar(session)

            duracion = (datetime.now() - inicio).total_seconds()
            avisos_totales += len(resultado.avisos)
            logger.info(
                f"[orquestrador] [{i}/{total}] {nombre} — "
                f"{len(resultado.avisos)} avisos, {resultado.errores} errores "
                f"({duracion:.1f}s)"
            )

            if i < total:
                logger.info(
                    f"[orquestrador] Pausa de {settings.delay_entre_scrapers_segundos}s "
                    "entre scrapers..."
                )
                await asyncio.sleep(settings.delay_entre_scrapers_segundos)

    duracion_ciclo = (datetime.now() - inicio_ciclo).total_seconds()
    logger.info(
        f"[orquestrador] Ciclo terminado — {avisos_totales} avisos totales "
        f"en {duracion_ciclo:.1f}s"
    )


def start_scheduler(intervalo_horas: int = 6) -> None:
    """Ejecuta un ciclo inmediato y luego repite cada intervalo_horas. Bloquea indefinidamente."""
    logger.info("[orquestrador] Ejecutando ciclo inicial antes de iniciar el scheduler...")
    asyncio.run(run_scrapers("all"))

    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: asyncio.run(run_scrapers("all")),
        "interval",
        hours=intervalo_horas,
    )
    logger.info(f"[orquestrador] Scheduler iniciado — ciclo cada {intervalo_horas}h")
    scheduler.start()
