import asyncio

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from carflip.database.session import AsyncSessionLocal
from carflip.scrapers.AutoCosmos.autocosmos import ScraperAutocosmos


_SCRAPERS = [
    ScraperAutocosmos,
]


async def run_all_scrapers() -> None:
    """Ejecuta todos los scrapers y sube los avisos a Supabase."""
    async with AsyncSessionLocal() as session:
        for scraper_cls in _SCRAPERS:
            scraper = scraper_cls()
            resultado = await scraper.ejecutar(session)
            logger.info(
                f"[runner] {resultado.fuente}: {len(resultado.avisos)} avisos, "
                f"{resultado.errores} errores"
            )


def start_scheduler(intervalo_horas: int = 6) -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: asyncio.run(run_all_scrapers()),
        "interval",
        hours=intervalo_horas,
    )
    logger.info(f"Scheduler iniciado — ciclo cada {intervalo_horas}h")
    scheduler.start()
