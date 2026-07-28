"""Crea el perfil de los usuarios anteriores al trigger de la 0010

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-28

`crear_perfil_al_registrarse` (0010) solo dispara en el INSERT de `auth.users`,
así que las cuentas que ya existían cuando se aplicó esa migración se quedaron
sin fila en `perfiles`. La 0010 no las rellenó.

Para esas cuentas, guardar los datos de contacto era un `UPDATE ... WHERE id =
<uuid>` sobre cero filas. PostgREST no lo trata como error, de modo que
`/api/cuenta/perfil` respondía "Datos guardados." mientras la página seguía
pidiendo completar nombre y teléfono (issue #43). El endpoint ya distingue ese
caso con un `select` posterior al UPDATE; esto arregla los datos.

El INSERT es idempotente —mismo `ON CONFLICT` que la función del trigger—, así
que puede volver a ejecutarse sin efecto. Solo crea la fila: nombre, teléfono,
región y comuna quedan nulos, que es como nace cualquier perfil.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BACKFILL = """
INSERT INTO public.perfiles (id)
SELECT id FROM auth.users
ON CONFLICT (id) DO NOTHING
"""


def upgrade() -> None:
    op.execute(_BACKFILL)


def downgrade() -> None:
    # Sin vuelta atrás a propósito: estas filas son indistinguibles de las que
    # crea el trigger, y borrar un perfil se lleva por CASCADE sus avisos, fotos,
    # revelaciones y reportes. El estado que deja `upgrade` es además el que la
    # 0010 debió dejar, así que no hay nada que revertir.
    pass
