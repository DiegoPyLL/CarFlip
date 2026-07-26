"""Agregar visible_en_deals a particulares_listings: opt-out de Deals

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-25

Hasta ahora, todo aviso de particular publicado entraba al pipeline de Deals
(candidatos.sql) y era evaluado por el LLM. Esta columna le da al dueño el
control: con visible_en_deals = false su aviso sigue publicado en el sitio pero
queda fuera de Deals y del LLM. Default true para no cambiar el comportamiento de
los avisos existentes.

Es propia del aviso de particular, así que no se toca ListingMixin ni las tablas
scrapeadas. No hace falta cambiar RLS ni grants: las políticas listings_*_propio
ya autorizan al dueño a escribir cualquier columna de su aviso.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLA = "particulares_listings"
_COLUMNA = "visible_en_deals"


def upgrade() -> None:
    op.add_column(
        _TABLA,
        sa.Column(_COLUMNA, sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column(_TABLA, _COLUMNA)
