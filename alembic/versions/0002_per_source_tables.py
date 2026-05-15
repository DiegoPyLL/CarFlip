"""Per-source listing tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-14

Reemplaza la tabla `listings` unificada (y `price_history` que dependía de ella)
por tablas individuales por scraper: autocosmos_listings, mercadolibre_listings.
El tracking de precios ahora es denormalizado dentro de cada tabla.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _crear_tabla_avisos(nombre: str) -> None:
    op.create_table(
        nombre,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_externo", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("precio", sa.Numeric(14, 2), nullable=True),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="CLP"),
        sa.Column("marca", sa.String(100), nullable=True),
        sa.Column("modelo", sa.String(100), nullable=True),
        sa.Column("anio", sa.Integer(), nullable=True),
        sa.Column("km", sa.Integer(), nullable=True),
        sa.Column("ubicacion", sa.String(200), nullable=True),
        sa.Column("combustible", sa.String(50), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("url_imagen", sa.Text(), nullable=True),
        sa.Column("disponible", sa.Boolean(), nullable=True),
        sa.Column("fecha_publicacion", sa.String(50), nullable=True),
        sa.Column("precio_anterior", sa.Numeric(14, 2), nullable=True),
        sa.Column("delta_pct", sa.Float(), nullable=True),
        sa.Column("primera_vez_visto", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ultima_vez_visto", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_externo", name=f"uq_{nombre}_id_externo"),
    )
    op.create_index(f"ix_{nombre}_precio", nombre, ["precio"])
    op.create_index(f"ix_{nombre}_marca", nombre, ["marca"])
    op.create_index(f"ix_{nombre}_modelo", nombre, ["modelo"])
    op.create_index(f"ix_{nombre}_anio", nombre, ["anio"])


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_price_drops")
    op.execute("DROP VIEW IF EXISTS v_market_comparison")

    # price_history tiene FK a listings, se elimina primero
    op.drop_table("price_history")
    op.drop_table("listings")

    _crear_tabla_avisos("autocosmos_listings")
    _crear_tabla_avisos("mercadolibre_listings")


def downgrade() -> None:
    op.drop_table("mercadolibre_listings")
    op.drop_table("autocosmos_listings")

    op.create_table(
        "listings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("km", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="CLP"),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("deal", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_price", sa.Numeric(14, 2), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_listings_source_external_id"),
    )
    op.create_index("ix_listings_source", "listings", ["source"])
    op.create_index("ix_listings_brand", "listings", ["brand"])
    op.create_index("ix_listings_model", "listings", ["model"])
    op.create_index("ix_listings_year", "listings", ["year"])
    op.create_index("ix_listings_price", "listings", ["price"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delta_pct", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute("""
        CREATE VIEW v_market_comparison AS
        SELECT brand, model, year,
            ROUND(AVG(price)::numeric, 0) AS avg_price,
            MIN(price) AS min_price, MAX(price) AS max_price,
            COUNT(*) AS total_listings
        FROM listings
        WHERE last_seen_at > NOW() - INTERVAL '7 days'
          AND price IS NOT NULL AND brand IS NOT NULL AND model IS NOT NULL AND year IS NOT NULL
        GROUP BY brand, model, year
    """)
    op.execute("""
        CREATE VIEW v_price_drops AS
        SELECT l.id, l.source, l.title, l.brand, l.model, l.year, l.km, l.url,
               ph.price AS new_price, ph.delta_pct, ph.recorded_at
        FROM price_history ph
        JOIN listings l ON l.id = ph.listing_id
        WHERE ph.delta_pct < -5 AND ph.recorded_at > NOW() - INTERVAL '7 days'
        ORDER BY ph.delta_pct ASC
    """)
