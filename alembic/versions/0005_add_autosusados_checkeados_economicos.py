"""Agregar tablas autosusados_listings, checkeados_listings y economicos_listings

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-12

Completa las fuentes HTML del roadmap Fase 5: los scrapers AutosusadosCloud,
CheckeadosCloud y EconomicosCloud declaran sus model_class respectivos y
necesitan tablas con la estructura compartida de ListingMixin: unique
constraint en id_externo + índices en precio, marca, modelo y anio.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLAS = ["autosusados_listings", "checkeados_listings", "economicos_listings"]


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
    for tabla in _TABLAS:
        _crear_tabla_avisos(tabla)


def downgrade() -> None:
    for tabla in reversed(_TABLAS):
        op.drop_table(tabla)
