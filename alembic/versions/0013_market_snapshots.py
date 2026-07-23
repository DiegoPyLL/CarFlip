"""Agregar tabla market_snapshots: agregado diario del mercado

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-23

price_history se eliminó en 0002 y el mercado quedó sin serie temporal. Esta
tabla la recupera a nivel agregado: una fila por día con precio
promedio/mediano/p25/p75, conteos y un payload JSONB con el detalle del día
(histograma, top marcas, mix de combustible) para graficar histórico más rico a
futuro sin nuevas migraciones.

La escribe snapshot_market() tras cada scrape con upsert sobre `fecha`
(idempotente: re-correr el mismo día actualiza la fila). Igual que las tablas de
listings, va sin RLS y sin grants para `anon`: la lee Astro en el servidor con
la SERVICE key para las tendencias de /mercado, y la escribe solo el pipeline
por conexión directa. Solo guarda agregados públicos (conteos y precios), sin
datos sensibles.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLA = "market_snapshots"


def upgrade() -> None:
    op.create_table(
        _TABLA,
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("precio_promedio", sa.Numeric(14, 2), nullable=True),
        sa.Column("precio_mediano", sa.Numeric(14, 2), nullable=True),
        sa.Column("precio_p25", sa.Numeric(14, 2), nullable=True),
        sa.Column("precio_p75", sa.Numeric(14, 2), nullable=True),
        sa.Column("nuevos_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("con_baja", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("por_fuente", postgresql.JSONB(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("fecha"),
    )


def downgrade() -> None:
    op.drop_table(_TABLA)
