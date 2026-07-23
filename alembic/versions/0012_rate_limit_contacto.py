"""Rate limit del formulario de contacto: registro de solicitudes por IP

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-23

El formulario público de contacto (`/api/contacto`) solo tenía un honeypot, que
no frena un script dirigido: un POST en bucle agota la cuota de Resend y satura
el buzón. Esta tabla registra cada intento por IP (hasheada) para contar los de
una ventana y cortar el exceso antes de llamar a Resend.

La escribe y lee únicamente el cliente de servicio (el formulario es anónimo, no
hay sesión sobre la que apoyar RLS). No se otorga a `anon` ni `authenticated`,
así que PostgREST no la expone; el `service_role` la alcanza porque bypassa RLS.
Se habilita RLS igual, como defensa en profundidad: sin políticas, nadie salvo
el servicio la toca.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contacto_solicitudes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # SHA-256 de la IP + un salt: no se guarda la IP en claro.
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    # El conteo filtra por IP y ventana temporal: el índice compuesto lo cubre.
    op.create_index(
        "ix_contacto_solicitudes_ip_creado",
        "contacto_solicitudes",
        ["ip_hash", "creado_en"],
    )
    op.execute("ALTER TABLE public.contacto_solicitudes ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("contacto_solicitudes")
