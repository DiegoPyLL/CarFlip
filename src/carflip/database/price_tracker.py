from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _delta_pct(old: Decimal | None, new: Decimal) -> float:
    if not old or old == 0:
        return 0.0
    return float((new - old) / old * 100)


async def get_market_summary(session: AsyncSession, brand: str, model: str, year: int) -> dict | None:
    """Retorna estadísticas de mercado para una combinación marca/modelo/año (últimos 7 días)."""
    sql = text("""
        SELECT
            AVG(precio)::numeric(14,0) AS avg_price,
            MIN(precio) AS min_price,
            MAX(precio) AS max_price,
            COUNT(*) AS total_listings
        FROM (
            SELECT precio FROM autocosmos_listings
            WHERE marca ILIKE :brand
              AND modelo ILIKE :model
              AND anio = :year
              AND ultima_vez_visto > NOW() - INTERVAL '7 days'
              AND precio IS NOT NULL
            UNION ALL
            SELECT precio FROM mercadolibre_listings
            WHERE marca ILIKE :brand
              AND modelo ILIKE :model
              AND anio = :year
              AND ultima_vez_visto > NOW() - INTERVAL '7 days'
              AND precio IS NOT NULL
        ) combined
    """)
    result = await session.execute(sql, {"brand": brand, "model": model, "year": year})
    row = result.mappings().one_or_none()
    if not row or not row["avg_price"]:
        return None
    return dict(row)
