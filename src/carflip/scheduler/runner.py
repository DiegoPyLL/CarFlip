import asyncio

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from carflip.database.session import AsyncSessionLocal
from carflip.scrapers.AutoCosmos.autocosmos import ScraperAutocosmos
from carflip.scrapers.AutoCosmos.autocosmosCloud import ScraperAutocosmosCloud
from carflip.scrapers.Yapo.yapo import ScraperYapo
from carflip.scrapers.Yapo.yapoCloud import ScraperYapoCloud

_SCRAPERS = {
    "autocosmos": ScraperAutocosmos,
    "autocosmosCloud": ScraperAutocosmosCloud,
    "yapo": ScraperYapo,
    "yapoCloud": ScraperYapoCloud,
}


async def run_scrapers(scraper_name: str = "all") -> None:
    """Ejecuta los scrapers seleccionados y sube los avisos a PostgreSQL."""
    async with AsyncSessionLocal() as session:
        if scraper_name == "all":
            to_run = _SCRAPERS.values()
        elif scraper_name in _SCRAPERS:
            to_run = [_SCRAPERS[scraper_name]]
        else:
            logger.error(f"Scraper no encontrado: {scraper_name}")
            return

        for scraper_cls in to_run:
            scraper = scraper_cls()
            resultado = await scraper.ejecutar(session)
            logger.info(
                f"[runner] {resultado.fuente}: {len(resultado.avisos)} avisos, "
                f"{resultado.errores} errores"
            )


def start_scheduler(intervalo_horas: int = 6) -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: asyncio.run(run_scrapers("all")),
        "interval",
        hours=intervalo_horas,
    )
    logger.info(f"Scheduler iniciado — ciclo cada {intervalo_horas}h")
    scheduler.start()
