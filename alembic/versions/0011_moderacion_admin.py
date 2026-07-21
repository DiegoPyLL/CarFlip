"""Moderación: políticas RLS para que un administrador accione los reportes

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-21

La 0010 dejó a un administrador leyendo `reportes_aviso` pero sin poder hacer
nada con ellos: no hay UPDATE sobre el reporte ni sobre el aviso ajeno, y el
SELECT de `particulares_listings` solo alcanza lo publicado o lo propio —así que
un aviso ya despublicado desaparecía de la bandeja de moderación.

Estas cuatro sentencias cierran ese hueco sin mover la autorización al código de
la aplicación: sigue viviendo en la base, apoyada en `app_metadata.rol`, que solo
escribe el servidor de Supabase. Son políticas permisivas adicionales, así que se
suman con OR a las de la 0010 y no alteran lo que puede hacer un usuario normal.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ES_ADMIN = "((SELECT auth.jwt()) -> 'app_metadata' ->> 'rol') = 'admin'"

_POLITICAS = {
    # Ver todos los estados: sin esto, despublicar un aviso lo hace invisible
    # para quien acaba de moderarlo y su reporte se cae de la bandeja.
    "listings_select_admin": f"""CREATE POLICY listings_select_admin ON public.particulares_listings
         FOR SELECT TO authenticated USING ({_ES_ADMIN})""",
    # Despublicar un aviso ajeno. El WITH CHECK repite la condición: sin él, el
    # UPDATE podría dejar una fila que la política ya no permitiría escribir.
    "listings_update_admin": f"""CREATE POLICY listings_update_admin ON public.particulares_listings
         FOR UPDATE TO authenticated
         USING ({_ES_ADMIN}) WITH CHECK ({_ES_ADMIN})""",
    # Cerrar el reporte una vez revisado.
    "reportes_update_admin": f"""CREATE POLICY reportes_update_admin ON public.reportes_aviso
         FOR UPDATE TO authenticated
         USING ({_ES_ADMIN}) WITH CHECK ({_ES_ADMIN})""",
}

# `particulares_listings` ya tenía UPDATE otorgado en la 0010; `reportes_aviso`
# solo SELECT e INSERT. Sin el GRANT, la política no basta.
_GRANT = "GRANT UPDATE ON public.reportes_aviso TO authenticated"


def upgrade() -> None:
    op.execute(_GRANT)
    for sentencia in _POLITICAS.values():
        op.execute(sentencia)


def downgrade() -> None:
    for nombre, _ in _POLITICAS.items():
        tabla = "reportes_aviso" if nombre.startswith("reportes") else "particulares_listings"
        op.execute(f"DROP POLICY IF EXISTS {nombre} ON public.{tabla}")
    op.execute("REVOKE UPDATE ON public.reportes_aviso FROM authenticated")
