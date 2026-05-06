"""
Lógica de upsert de listings y registro de cambios de precio.
Detecta si un aviso ya existe, actualiza su precio y guarda el historial.
"""

from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.config import settings
from carflip.database.models import Listing, PriceHistory, ScrapedRun
from carflip.scrapers.base import CarListing, ScrapeResult


async def upsert_listings(session: AsyncSession, result: ScrapeResult) -> None:
    """Persiste los listings de un ScrapeResult, registrando cambios de precio."""
    run = ScrapedRun(
        source=result.source,
        started_at=result.started_at,
        finished_at=result.finished_at or datetime.now(),
        items_found=len(result.listings),
        errors=result.errors,
    )
    session.add(run)

    for item in result.listings:
        await _upsert_one(session, item)

    await session.commit()
    logger.info(f"[{result.source}] {len(result.listings)} listings persistidos")


async def _upsert_one(session: AsyncSession, item: CarListing) -> None:
    stmt = select(Listing).where(
        Listing.source == item.source,
        Listing.external_id == item.external_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        if item.price is not None and item.price != existing.price:
            delta_pct = _delta_pct(existing.price, item.price)
            session.add(PriceHistory(
                listing_id=existing.id,
                price=item.price,
                delta_pct=delta_pct,
            ))
            logger.debug(
                f"[{item.source}] Precio cambiado en {item.external_id}: "
                f"{existing.price} → {item.price} ({delta_pct:+.1f}%)"
            )
            existing.last_price = existing.price
            existing.price = item.price

        existing.last_seen_at = datetime.now()
        existing.title = item.title
        existing.url = item.url
        if item.km:
            existing.km = item.km
        if item.location:
            existing.location = item.location
    else:
        listing = Listing(
            source=item.source,
            external_id=item.external_id,
            url=item.url,
            title=item.title,
            brand=item.brand,
            model=item.model,
            year=item.year,
            km=item.km,
            price=item.price,
            currency=item.currency,
            location=item.location,
            last_price=item.price,
        )
        session.add(listing)


def _delta_pct(old: Decimal | None, new: Decimal) -> float:
    if not old or old == 0:
        return 0.0
    return float((new - old) / old * 100)


async def mark_deals(session: AsyncSession) -> int:
    """
    Marca como deal=true los listings cuyo precio es menor al promedio del
    mercado (misma marca/modelo/año) menos el threshold configurado.
    Retorna cuántos deals se marcaron.
    """
    threshold = settings.deal_threshold_pct
    sql = text("""
        UPDATE listings l
        SET deal = true
        FROM (
            SELECT brand, model, year, AVG(price) AS avg_price
            FROM listings
            WHERE last_seen_at > NOW() - INTERVAL '7 days'
              AND price IS NOT NULL AND brand IS NOT NULL AND model IS NOT NULL AND year IS NOT NULL
            GROUP BY brand, model, year
        ) m
        WHERE l.brand = m.brand
          AND l.model = m.model
          AND l.year = m.year
          AND l.price IS NOT NULL
          AND l.price < m.avg_price * (1 - :threshold / 100.0)
          AND l.deal = false
        RETURNING l.id
    """)
    result = await session.execute(sql, {"threshold": threshold})
    await session.commit()
    count = result.rowcount
    if count:
        logger.info(f"{count} listings marcados como deal (>{threshold}% bajo promedio de mercado)")
    return count


async def get_market_summary(session: AsyncSession, brand: str, model: str, year: int) -> dict | None:
    """Retorna estadísticas de mercado para una combinación marca/modelo/año."""
    sql = text("""
        SELECT
            AVG(price)::numeric(14,0) AS avg_price,
            MIN(price) AS min_price,
            MAX(price) AS max_price,
            COUNT(*) AS total_listings
        FROM listings
        WHERE brand ILIKE :brand
          AND model ILIKE :model
          AND year = :year
          AND last_seen_at > NOW() - INTERVAL '7 days'
          AND price IS NOT NULL
    """)
    result = await session.execute(sql, {"brand": brand, "model": model, "year": year})
    row = result.mappings().one_or_none()
    if not row or not row["avg_price"]:
        return None
    return dict(row)
