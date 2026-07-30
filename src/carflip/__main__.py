"""
CLI de CarFlip.

Comandos:
  carflip market   — muestra precio promedio/min/max para marca/modelo/año
  carflip deals    — detecta y categoriza oportunidades de compra (SQL + Groq)
  carflip snapshot — persiste el agregado de mercado del día (tendencias de /mercado)
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
    """CarFlip — análisis de precios del mercado chileno de autos usados."""
    _setup_logging()


@cli.command()
def deals() -> None:
    """Detecta y categoriza oportunidades de compra (SQL + Groq)."""
    from carflip.database.session import AsyncSessionLocal
    from carflip.deals.detector import detectar_deals

    async def _run():
        async with AsyncSessionLocal() as session:
            return await detectar_deals(session)

    activos = asyncio.run(_run())
    click.echo(f"Deals activos: {activos}")


@cli.command()
def snapshot() -> None:
    """Persiste el agregado de mercado del día en market_snapshots (idempotente)."""
    from carflip.database.session import AsyncSessionLocal
    from carflip.database.snapshot import snapshot_market

    async def _run():
        async with AsyncSessionLocal() as session:
            return await snapshot_market(session)

    fecha = asyncio.run(_run())
    click.echo(f"Snapshot de mercado escrito para {fecha}")


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
