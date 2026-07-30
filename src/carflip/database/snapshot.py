"""Snapshot diario del mercado.

Escribe una fila en `market_snapshots` con los agregados del día (precio
promedio/mediano/p25/p75, conteos y un payload con las top marcas). Lo corre el
CLI `carflip snapshot`.

Todo el cálculo se hace en SQL (COUNT/AVG/percentile_cont) en vez de traer filas
y reducir en Python: es una sola pasada por la base y espeja el patrón de
percentiles de deals/candidatos.sql. El upsert es idempotente sobre `fecha`, así
que re-correr el mismo día actualiza la fila.
"""

from datetime import date, datetime, timezone

from loguru import logger
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.database.models import MarketSnapshot

# Solo los avisos publicados: los pausados y vendidos no son oferta vigente,
# igual que en candidatos.sql.
_FUENTE = "particular"
_WHERE_VIGENTES = "estado = 'publicado'"

_SQL_CONTEOS = f"""
SELECT count(*) AS total,
       count(*) FILTER (WHERE primera_vez_visto >= now() - interval '24 hours') AS nuevos_24h,
       count(*) FILTER (WHERE delta_pct < 0) AS con_baja
FROM particulares_listings
WHERE {_WHERE_VIGENTES}
"""

_SQL_PRECIOS = f"""
SELECT round(avg(precio), 2) AS promedio,
       round(percentile_cont(0.25) WITHIN GROUP (ORDER BY precio)::numeric, 2) AS p25,
       round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY precio)::numeric, 2) AS mediana,
       round(percentile_cont(0.75) WITHIN GROUP (ORDER BY precio)::numeric, 2) AS p75
FROM particulares_listings
WHERE {_WHERE_VIGENTES} AND precio > 0
"""

_SQL_TOP_MARCAS = f"""
SELECT marca,
       count(*) AS total,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY precio)
             FILTER (WHERE precio > 0)::numeric, 0) AS mediana
FROM particulares_listings
WHERE {_WHERE_VIGENTES} AND marca IS NOT NULL
GROUP BY marca
ORDER BY count(*) DESC
LIMIT 12
"""


async def snapshot_market(session: AsyncSession) -> date:
    """Calcula y persiste el agregado de mercado de hoy. Retorna la fecha escrita."""
    hoy = datetime.now(timezone.utc).date()

    conteos = (await session.execute(text(_SQL_CONTEOS))).mappings().one()
    precios = (await session.execute(text(_SQL_PRECIOS))).mappings().one()
    top_marcas = (await session.execute(text(_SQL_TOP_MARCAS))).mappings().all()

    total = conteos["total"]
    # `por_fuente` se conserva porque las filas históricas lo usan y porque un
    # catálogo de automotora entraría como una fuente más sin cambiar el esquema.
    por_fuente = {_FUENTE: total}

    # Decimal no es JSON-serializable: la mediana va a float antes del JSONB.
    payload = {
        "top_marcas": [
            {
                "marca": r["marca"],
                "total": r["total"],
                "mediana": float(r["mediana"]) if r["mediana"] is not None else None,
            }
            for r in top_marcas
        ],
    }

    valores = {
        "fecha": hoy,
        "total": total,
        "precio_promedio": precios["promedio"],
        "precio_mediano": precios["mediana"],
        "precio_p25": precios["p25"],
        "precio_p75": precios["p75"],
        "nuevos_24h": conteos["nuevos_24h"],
        "con_baja": conteos["con_baja"],
        "por_fuente": por_fuente,
        "payload": payload,
    }

    stmt = insert(MarketSnapshot).values(**valores)
    stmt = stmt.on_conflict_do_update(
        index_elements=["fecha"],
        set_={
            "total": stmt.excluded.total,
            "precio_promedio": stmt.excluded.precio_promedio,
            "precio_mediano": stmt.excluded.precio_mediano,
            "precio_p25": stmt.excluded.precio_p25,
            "precio_p75": stmt.excluded.precio_p75,
            "nuevos_24h": stmt.excluded.nuevos_24h,
            "con_baja": stmt.excluded.con_baja,
            "por_fuente": stmt.excluded.por_fuente,
            "payload": stmt.excluded.payload,
            "creado_en": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()

    logger.info(f"[snapshot] {hoy} — {total} avisos, mediana {precios['mediana']}")
    return hoy
