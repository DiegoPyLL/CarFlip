"""Eliminar tabla economicos_listings

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-12

El sitio economicos.cl bloquea el scraping (anti-bot), por lo que la fuente
Económicos se elimina del proyecto: se borra el scraper, su model_class y esta
tabla. El downgrade recrea la tabla con la estructura compartida de ListingMixin
(misma definición que en la migración 0006) por si se quisiera revertir.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLA = "economicos_listings"


def upgrade() -> None:
    op.drop_table(_TABLA)


def downgrade() -> None:
    op.create_table(
        _TABLA,
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
        sa.UniqueConstraint("id_externo", name=f"uq_{_TABLA}_id_externo"),
    )
    op.create_index(f"ix_{_TABLA}_precio", _TABLA, ["precio"])
    op.create_index(f"ix_{_TABLA}_marca", _TABLA, ["marca"])
    op.create_index(f"ix_{_TABLA}_modelo", _TABLA, ["modelo"])
    op.create_index(f"ix_{_TABLA}_anio", _TABLA, ["anio"])
