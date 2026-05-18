"""
CLI de CarFlip.

Comandos:
  carflip start   — inicia el scheduler automático (cada 6h)
  carflip run     — ejecuta todos los scrapers una vez
  carflip market  — muestra precio promedio/min/max para marca/modelo/año
"""

import asyncio
import sys

import click
from loguru import logger

from carflip.config import settings


def _setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    logger.add(settings.log_file, level="DEBUG", rotation="10 MB", retention="30 days", enqueue=True)


@click.group()
def cli() -> None:
    """CarFlip — scraper automático de portales de venta de autos."""
    _setup_logging()


@cli.command()
def start() -> None:
    """Inicia el scheduler automático."""
    from carflip.scheduler.runner import run_scrapers, start_scheduler
    logger.info("Ejecutando primer ciclo antes de iniciar el scheduler...")
    asyncio.run(run_scrapers("all"))
    start_scheduler(settings.scrape_interval_hours)


@cli.command("run")
@click.option("--scraper", default=None, help="Nombre del scraper a ejecutar (ej. autocosmosCloud)")
def run_once(scraper: str | None) -> None:
    """Ejecuta todos los scrapers o uno específico."""
    from carflip.scheduler.runner import _SCRAPERS, run_scrapers
    
    if scraper is None:
        click.echo("Scrapers disponibles:")
        click.echo("0. Todos")
        scraper_names = list(_SCRAPERS.keys())
        for i, name in enumerate(scraper_names):
            click.echo(f"{i + 1}. {name}")
            
        opcion = click.prompt("\nSeleccione qué ejecutar", type=int, default=0)
        if opcion == 0:
            scraper = "all"
        elif 1 <= opcion <= len(scraper_names):
            scraper = scraper_names[opcion - 1]
        else:
            click.echo("Opción inválida.")
            return

    asyncio.run(run_scrapers(scraper))


@cli.command()
@click.argument("brand")
@click.argument("model")
@click.argument("year", type=int)
def market(brand: str, model: str, year: int) -> None:
    """Muestra estadísticas de mercado para una combinación marca/modelo/año."""
    from carflip.database.price_tracker import get_market_summary
    from carflip.database.session import AsyncSessionLocal

    async def _run():
        async with AsyncSessionLocal() as session:
            data = await get_market_summary(session, brand, model, year)
            if not data:
                click.echo(f"Sin datos para {brand} {model} {year} en los últimos 7 días")
                return
            click.echo(f"\n{brand} {model} {year}")
            click.echo(f"  Promedio:  ${data['avg_price']:,.0f}")
            click.echo(f"  Mínimo:    ${data['min_price']:,.0f}")
            click.echo(f"  Máximo:    ${data['max_price']:,.0f}")
            click.echo(f"  Avisos:    {data['total_listings']}")

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
