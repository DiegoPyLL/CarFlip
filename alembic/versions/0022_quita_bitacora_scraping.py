"""Eliminar la bitácora de scraping: scrape_runs y run_fail_logs

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-29

Los cuatro scrapers (Autocosmos, Yapo, Autosusados, Checkeados) se retiraron:
CarFlip aloja los avisos de particulares y los catálogos de automotoras con
acuerdo, así que ya no hay corridas de ingesta que registrar. Sin escritor y sin
lector, estas dos tablas solo eran ruido en el esquema.

Las cinco tablas de avisos scrapeados (autocosmos_listings, yapo_listings,
autosusados_listings, checkeados_listings, mercadolibre_listings) NO se tocan a
propósito: se conservan con sus datos como registro de esa etapa.

`deals` tampoco se limpia acá. Las filas de fuentes scrapeadas se desactivan
solas en la primera corrida de `carflip deals`: `_desactivar_obsoletos()` pone
activo = false a todo deal que no aparezca entre los candidatos, y candidatos.sql
ya solo devuelve particulares.

El downgrade recrea la estructura, no los datos: las corridas registradas se
pierden de forma definitiva.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # run_fail_logs primero: tiene la FK contra scrape_runs.
    op.drop_index("ix_run_fail_logs_etapa", table_name="run_fail_logs")
    op.drop_index("ix_run_fail_logs_run_id", table_name="run_fail_logs")
    op.drop_table("run_fail_logs")
    op.drop_table("scrape_runs")


def downgrade() -> None:
    # Estructura acumulada por 0001 (base), 0008 (métricas del run_report y la
    # unique que hacía idempotente la carga) y 0009 (bytes AVIF).
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duracion_segundos", sa.Float(), nullable=True),
        sa.Column("paginas_procesadas", sa.Integer(), nullable=True),
        sa.Column("avisos_encontrados", sa.Integer(), nullable=True),
        sa.Column("avisos_unicos", sa.Integer(), nullable=True),
        sa.Column("avisos_validos", sa.Integer(), nullable=True),
        sa.Column("avisos_rechazados", sa.Integer(), nullable=True),
        sa.Column("bytes_fotos_originales", sa.BigInteger(), nullable=True),
        sa.Column("bytes_fotos_avif", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "started_at", name="uq_scrape_runs_source_started_at"),
    )

    op.create_table(
        "run_fail_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("fuente", sa.String(50), nullable=False),
        sa.Column("etapa", sa.String(50), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("id_externo", sa.String(200), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["scrape_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_fail_logs_run_id", "run_fail_logs", ["run_id"])
    op.create_index("ix_run_fail_logs_etapa", "run_fail_logs", ["etapa"])
