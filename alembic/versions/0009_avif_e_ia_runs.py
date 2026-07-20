"""Agregar bytes AVIF a scrape_runs y crear ia_runs

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-13

bytes_fotos_originales / bytes_fotos_avif en scrape_runs habilitan el KPI de
Eficiencia de Compresión AVIF (meta >= 60%) del documento de Monitoreo.

ia_runs registra cada lote enviado a Groq (categorización de deals): duración,
candidatos enviados, evaluaciones válidas y descartes por formato — habilita
los KPIs de Tiempo de respuesta del Agente IA (< 3s/aviso) y Tasa de error de
formato (< 2%).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("bytes_fotos_originales", sa.BigInteger(), nullable=True))
    op.add_column("scrape_runs", sa.Column("bytes_fotos_avif", sa.BigInteger(), nullable=True))

    op.create_table(
        "ia_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("duracion_segundos", sa.Float(), nullable=False),
        sa.Column("candidatos_enviados", sa.Integer(), nullable=False),
        sa.Column("evaluaciones_validas", sa.Integer(), nullable=False),
        sa.Column("lotes_descartados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("modelo_ia", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ia_runs_started_at", "ia_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_ia_runs_started_at", table_name="ia_runs")
    op.drop_table("ia_runs")
    op.drop_column("scrape_runs", "bytes_fotos_avif")
    op.drop_column("scrape_runs", "bytes_fotos_originales")
