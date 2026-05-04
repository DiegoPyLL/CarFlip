import asyncio

from loguru import logger

from carflipper.database import price_tracker
from carflipper.database.session import AsyncSessionLocal
from carflipper.scrapers.autosusados import AutosUsadosScraper
from carflipper.scrapers.chileautos import ChileautosScraper
from carflipper.scrapers.facebook import FacebookScraper
from carflipper.scrapers.mercadolibre import MercadoLibreScraper
from carflipper.scrapers.yapo import YapoScraper


async def run_all_scrapers() -> None:
    """Ejecuta todos los scrapers en secuencia y persiste los resultados."""
    logger.info("=== Inicio de ciclo de scraping ===")

    async with AsyncSessionLocal() as session:
        scrapers = [
            MercadoLibreScraper(),
            AutosUsadosScraper(),
            ChileautosScraper(),
            YapoScraper(),
            FacebookScraper(session),
        ]

        for scraper in scrapers:
            result = await scraper.run(session)
            await price_tracker.upsert_listings(session, result)

        deals_marked = await price_tracker.mark_deals(session)
        logger.info(f"=== Ciclo completo — {deals_marked} nuevos deals detectados ===")


def start_scheduler(interval_hours: int) -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_all_scrapers,
        trigger="interval",
        hours=interval_hours,
        id="scrape_all",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler iniciado — ejecutando cada {interval_hours} horas")

    loop = asyncio.get_event_loop()
    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler detenido")
