"""Catálogo normalizado de marcas, modelos y versiones (issue #64)

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-31

Hasta acá marca, modelo y versión eran texto libre en el formulario de aviso, y
toda la normalización ocurría al leer: `slugModelo` colapsa "Serie 3", "Serie-3"
y "Serie/3" en una sola página, y `ModeloListado.grafias` guarda cada escritura
para poder consultarlas. Con 17 avisos eso no se nota; con miles, cada grafía
extra parte los avisos de un mismo modelo entre URLs que compiten y ensucia las
estadísticas de mercado.

Estas dos tablas mueven la normalización al origen: el formulario ofrece un
catálogo cerrado de marca y modelo, y el servidor escribe la grafía canónica que
sale de acá —no la que teclee el usuario—. La versión sigue admitiendo texto
libre (un importado no está en ninguna lista), pero cuando coincide con una del
catálogo aporta además su ficha: combustible, transmisión y tracción, que el
formulario autocompleta.

Son dos tablas y no una plana porque repetir la marca en cada versión son
decenas de miles de filas con el mismo texto, y el formulario carga los modelos
sin necesitar las versiones.

Permisos: RLS activa sin políticas y sin GRANT a anon/authenticated. El catálogo
lo lee Astro en el servidor con la SERVICE key, que bypassa RLS; es el criterio
que fijó la 0014 y que estas tablas no deben reabrir.

Los datos no vienen en la migración: los carga `scripts/catalogo/cargar_catalogo.py`
desde `data/catalogo/vehiculos.json`, de forma idempotente y re-ejecutable cada
vez que el catálogo crece.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Los tres dominios duplican COMBUSTIBLES, TRANSMISIONES y TRACCIONES de
# `web/src/lib/publicaciones/opciones.ts`. Es la misma duplicación inevitable al
# cruzar de lenguaje que documenta la 0018: la aplicación valida primero y da el
# mensaje bueno, esto es la red que la respalda.
_CHECKS = {
    "ck_catalogo_versiones_combustible": (
        "combustible IS NULL OR combustible IN ('Bencina', 'Diésel', 'Híbrido', 'Eléctrico', 'Gas')"
    ),
    "ck_catalogo_versiones_transmision": "transmision IS NULL OR transmision IN ('Manual', 'Automática')",
    "ck_catalogo_versiones_traccion": "traccion IS NULL OR traccion IN ('4x4', 'Delantera', 'Trasera')",
    # El mismo rango que `ck_particulares_anio`: un año de catálogo que no puede
    # ser el de un aviso no describe nada publicable.
    "ck_catalogo_versiones_anios": (
        "(anio_desde IS NULL OR (anio_desde >= 1950 AND anio_desde <= 2100)) AND "
        "(anio_hasta IS NULL OR (anio_hasta >= 1950 AND anio_hasta <= 2100)) AND "
        "(anio_desde IS NULL OR anio_hasta IS NULL OR anio_hasta >= anio_desde)"
    ),
}

_TABLAS = ("catalogo_versiones", "catalogo_modelos")


def upgrade() -> None:
    op.create_table(
        "catalogo_modelos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # La grafía canónica, la que termina escrita en el aviso: "Kia", "CX-5".
        sa.Column("marca", sa.String(100), nullable=False),
        sa.Column("modelo", sa.String(100), nullable=False),
        # Los slugs son los que producen `agruparMarcas` (marca en minúsculas) y
        # `slugModelo` en `web/src/lib/marcas.ts`. Se guardan en vez de calcularse
        # al vuelo porque son la clave de identidad: dos filas que dan el mismo
        # slug son el mismo modelo escrito de dos formas, justo lo que esto
        # existe para impedir.
        sa.Column("marca_slug", sa.String(100), nullable=False),
        sa.Column("modelo_slug", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marca_slug", "modelo_slug", name="uq_catalogo_modelos_slug"),
    )
    op.create_index("ix_catalogo_modelos_marca_slug", "catalogo_modelos", ["marca_slug"])

    op.create_table(
        "catalogo_versiones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("modelo_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("combustible", sa.String(20), nullable=True),
        sa.Column("transmision", sa.String(20), nullable=True),
        sa.Column("traccion", sa.String(20), nullable=True),
        sa.Column("anio_desde", sa.SmallInteger(), nullable=True),
        sa.Column("anio_hasta", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(["modelo_id"], ["catalogo_modelos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("modelo_id", "version", name="uq_catalogo_versiones_modelo_version"),
    )
    op.create_index("ix_catalogo_versiones_modelo_id", "catalogo_versiones", ["modelo_id"])

    for nombre, condicion in _CHECKS.items():
        op.create_check_constraint(nombre, "catalogo_versiones", condicion)

    for tabla in _TABLAS:
        op.execute(f"ALTER TABLE public.{tabla} ENABLE ROW LEVEL SECURITY")
        # Cinturón sobre los tirantes de la 0014: si el DEFAULT PRIVILEGES de
        # `supabase_admin` —el que ese arreglo no pudo tocar— alcanzara a estas
        # tablas, nacerían abiertas a la anon key, que es pública por diseño.
        op.execute(f"REVOKE ALL ON public.{tabla} FROM anon, authenticated")
        op.execute(f"REVOKE ALL ON SEQUENCE public.{tabla}_id_seq FROM anon, authenticated")


def downgrade() -> None:
    op.drop_table("catalogo_versiones")
    op.drop_table("catalogo_modelos")
