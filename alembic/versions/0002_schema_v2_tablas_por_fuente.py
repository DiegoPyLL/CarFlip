"""Schema v2: tablas por fuente con columnas en español

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-23

Reemplaza la tabla unificada 'listings' (inglés) por tablas separadas
por fuente con columnas en español, alineadas con AvisoAuto y ListingMixin.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLAS_NUEVAS = (
    "autocosmos_listings",
    "mercadolibre_listings",
    "yapo_listings",
)


def _columnas_listing() -> list:
    return [
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
    ]


def upgrade() -> None:
    # ── Eliminar schema viejo ─────────────────────────────────────────────────
    op.execute("DROP VIEW IF EXISTS v_price_drops")
    op.execute("DROP VIEW IF EXISTS v_market_comparison")
    op.drop_table("session_cookies")
    op.drop_table("price_history")
    op.drop_table("listings")

    # ── Crear tablas por fuente ───────────────────────────────────────────────
    for tabla in _TABLAS_NUEVAS:
        op.create_table(
            tabla,
            *_columnas_listing(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("id_externo", name=f"uq_{tabla}_id_externo"),
        )
        op.create_index(f"ix_{tabla}_precio", tabla, ["precio"])
        op.create_index(f"ix_{tabla}_marca", tabla, ["marca"])
        op.create_index(f"ix_{tabla}_modelo", tabla, ["modelo"])
        op.create_index(f"ix_{tabla}_anio", tabla, ["anio"])


def downgrade() -> None:
    for tabla in _TABLAS_NUEVAS:
        op.drop_table(tabla)
