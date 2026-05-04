"""
CLI de CarFlipper.

Comandos:
  carflipper start              — inicia el scheduler automático (cada 6h)
  carflipper run                — ejecuta todos los scrapers una vez
  carflipper credentials set    — guarda credenciales de un sitio en el llavero del OS
  carflipper credentials delete — elimina credenciales de un sitio
  carflipper market             — muestra precio promedio/min/max para marca/modelo/año
"""

import asyncio
import sys

import click
from loguru import logger

from carflipper.config import settings
from carflipper import credentials as creds_module


def _setup_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    if not settings.use_secrets_manager:
        logger.add(settings.log_file, level="DEBUG", rotation="10 MB", retention="30 days", enqueue=True)


@click.group()
def cli() -> None:
    """CarFlipper — scraper automático de portales de venta de autos."""
    _setup_logging()


@cli.command()
def start() -> None:
    """Inicia el scheduler automático."""
    from carflipper.scheduler.runner import run_all_scrapers, start_scheduler
    logger.info("Ejecutando primer ciclo antes de iniciar el scheduler...")
    asyncio.run(run_all_scrapers())
    start_scheduler(settings.scrape_interval_hours)


@cli.command("run")
def run_once() -> None:
    """Ejecuta todos los scrapers una sola vez."""
    from carflipper.scheduler.runner import run_all_scrapers
    asyncio.run(run_all_scrapers())


@cli.group()
def credentials() -> None:
    """Gestión de credenciales de sitios."""


@credentials.command("set")
@click.argument("source")
@click.argument("email")
@click.argument("password")
def credentials_set(source: str, email: str, password: str) -> None:
    """Guarda credenciales en el llavero del OS.\n\nEjemplo: carflipper credentials set facebook user@email.com pass123"""
    creds_module.set_credentials(source, email, password)
    click.echo(f"Credenciales guardadas para {source}")


@credentials.command("delete")
@click.argument("source")
def credentials_delete(source: str) -> None:
    """Elimina las credenciales de un sitio."""
    creds_module.delete_credentials(source)


@credentials.command("list")
def credentials_list() -> None:
    """Muestra qué sitios tienen credenciales configuradas."""
    configured = creds_module.list_configured_sources()
    for source, has in configured.items():
        status = "✓" if has else "✗"
        click.echo(f"  {status} {source}")


@cli.command()
@click.argument("brand")
@click.argument("model")
@click.argument("year", type=int)
def market(brand: str, model: str, year: int) -> None:
    """Muestra estadísticas de mercado para una combinación marca/modelo/año."""
    from carflipper.database.price_tracker import get_market_summary
    from carflipper.database.session import AsyncSessionLocal

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
