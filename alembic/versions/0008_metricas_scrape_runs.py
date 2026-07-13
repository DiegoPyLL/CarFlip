"""Ampliar scrape_runs con métricas del run_report y agregar run_fail_logs

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-13

scrape_runs existía desde 0001 pero ningún código la escribía. Se amplía con
las métricas que cada scraper Cloud ya calcula en su run_report.json (duración,
páginas, conteos del embudo encontrados→únicos→válidos) más una unique
constraint (source, started_at) que hace idempotente la carga desde S3.

run_fail_logs persiste cada FAIL LOG individual (etapa, motivo, id_externo)
con FK a su corrida, para poder desglosar fallas por etapa en el dashboard.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("duracion_segundos", sa.Float(), nullable=True))
    op.add_column("scrape_runs", sa.Column("paginas_procesadas", sa.Integer(), nullable=True))
    op.add_column("scrape_runs", sa.Column("avisos_encontrados", sa.Integer(), nullable=True))
    op.add_column("scrape_runs", sa.Column("avisos_unicos", sa.Integer(), nullable=True))
    op.add_column("scrape_runs", sa.Column("avisos_validos", sa.Integer(), nullable=True))
    op.add_column("scrape_runs", sa.Column("avisos_rechazados", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        "uq_scrape_runs_source_started_at", "scrape_runs", ["source", "started_at"]
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


def downgrade() -> None:
    op.drop_index("ix_run_fail_logs_etapa", table_name="run_fail_logs")
    op.drop_index("ix_run_fail_logs_run_id", table_name="run_fail_logs")
    op.drop_table("run_fail_logs")
    op.drop_constraint("uq_scrape_runs_source_started_at", "scrape_runs", type_="unique")
    op.drop_column("scrape_runs", "avisos_rechazados")
    op.drop_column("scrape_runs", "avisos_validos")
    op.drop_column("scrape_runs", "avisos_unicos")
    op.drop_column("scrape_runs", "avisos_encontrados")
    op.drop_column("scrape_runs", "paginas_procesadas")
    op.drop_column("scrape_runs", "duracion_segundos")
