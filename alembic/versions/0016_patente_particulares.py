"""Agregar patente a particulares_listings

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-26

La patente pasa a ser obligatoria al publicar o editar un aviso de particular
(formatos de la Ley 18.290 y el D.S. 17 del MTT: 6 caracteres un auto, 5 una
moto). Se guarda canónica: mayúsculas y sin separadores.

La columna queda nullable a propósito: los avisos creados antes de esta
exigencia no tienen patente y siguen siendo válidos; la obligatoriedad la
impone la validación del formulario, no la base. No hace falta cambiar RLS ni
GRANT: las políticas listings_*_propio ya autorizan al dueño a escribir
cualquier columna de su aviso.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLA = "particulares_listings"
_COLUMNA = "patente"


def upgrade() -> None:
    op.add_column(_TABLA, sa.Column(_COLUMNA, sa.String(6), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLA, _COLUMNA)
