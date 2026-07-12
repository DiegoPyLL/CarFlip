"""Agregar tabla deals

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-11

Tabla de oportunidades de compra: snapshot del aviso detectado como outlier
de precio por candidatos.sql + contexto de mercado (mediana del grupo
comparable) + evaluación del LLM (Groq): categoria, puntaje, riesgos, resumen.
Clave única compuesta (fuente, id_externo) — un mismo aviso solo puede ser
un deal a la vez, sin importar cuántas corridas lo detecten.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLA = "deals"


def upgrade() -> None:
    op.create_table(
        _TABLA,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # Snapshot del aviso
        sa.Column("fuente", sa.String(50), nullable=False),
        sa.Column("id_externo", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("marca", sa.String(100), nullable=True),
        sa.Column("modelo", sa.String(100), nullable=True),
        sa.Column("anio", sa.Integer(), nullable=True),
        sa.Column("km", sa.Integer(), nullable=True),
        sa.Column("ubicacion", sa.String(200), nullable=True),
        sa.Column("precio", sa.Numeric(14, 2), nullable=False),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="CLP"),
        sa.Column("url_imagen", sa.Text(), nullable=True),
        # Contexto de mercado
        sa.Column("precio_mercado", sa.Numeric(14, 2), nullable=True),
        sa.Column("pct_vs_mercado", sa.Float(), nullable=True),
        sa.Column("delta_pct", sa.Float(), nullable=True),
        sa.Column("comparables", sa.Integer(), nullable=True),
        # Evaluación IA
        sa.Column("categoria", sa.String(30), nullable=True),
        sa.Column("puntaje", sa.Integer(), nullable=True),
        sa.Column("riesgos", JSONB(), nullable=True),
        sa.Column("resumen", sa.Text(), nullable=True),
        sa.Column("modelo_ia", sa.String(100), nullable=True),
        sa.Column("categorizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("precio_al_categorizar", sa.Numeric(14, 2), nullable=True),
        # Estado
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fuente", "id_externo", name=f"uq_{_TABLA}_fuente_id_externo"),
    )
    op.create_index(f"ix_{_TABLA}_categoria", _TABLA, ["categoria"])
    op.create_index(f"ix_{_TABLA}_puntaje", _TABLA, ["puntaje"])
    op.create_index(f"ix_{_TABLA}_activo", _TABLA, ["activo"])


def downgrade() -> None:
    op.drop_table(_TABLA)
