"""Agregar transmision y traccion a todas las fuentes y a deals

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-26

`transmision` existía solo en particulares_listings; sube a ListingMixin para
que las cinco fuentes scrapeadas también la tengan y el filtro cruzado funcione.
`traccion` (4x4 / Delantera / Trasera) es nueva en las seis tablas. `deals`
recibe ambas porque su fila es un snapshot del aviso.

Los valores los canoniza el pipeline al escribir (normalizar_transmision y
normalizar_traccion en scrapers/base.py); la web filtra por igualdad exacta.
Nullable a propósito: no toda fuente publica el dato. No hace falta cambiar RLS
ni GRANT: los permisos son por tabla, no por columna, y las políticas
listings_*_propio ya autorizan al dueño a escribir cualquier columna de su aviso.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLAS_SCRAPEADAS = [
    "autocosmos_listings",
    "mercadolibre_listings",
    "yapo_listings",
    "autosusados_listings",
    "checkeados_listings",
]

# particulares_listings ya tiene transmision (0010); solo le falta traccion.
_TABLAS_TRACCION = _TABLAS_SCRAPEADAS + ["particulares_listings", "deals"]
_TABLAS_TRANSMISION = _TABLAS_SCRAPEADAS + ["deals"]


def upgrade() -> None:
    for tabla in _TABLAS_TRANSMISION:
        op.add_column(tabla, sa.Column("transmision", sa.String(50), nullable=True))
    for tabla in _TABLAS_TRACCION:
        op.add_column(tabla, sa.Column("traccion", sa.String(20), nullable=True))


def downgrade() -> None:
    for tabla in _TABLAS_TRACCION:
        op.drop_column(tabla, "traccion")
    for tabla in _TABLAS_TRANSMISION:
        op.drop_column(tabla, "transmision")
