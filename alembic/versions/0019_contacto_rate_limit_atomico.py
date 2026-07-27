"""Rate limit del contacto en una sola función atómica

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-26

El limitador de `/api/contacto` que introdujo la 0012 se aplicaba en dos pasos
desde la web: un `select count` y después un `insert`. Eso deja tres agujeros:

1. La fila se insertaba siempre, incluso cuando la petición ya había superado el
   tope, así que un anónimo podía hacer crecer `contacto_solicitudes` sin límite.
2. Contar y luego insertar no es atómico: bajo concurrencia se colaban más
   solicitudes que el tope.
3. Nadie borraba las filas viejas, que solo sirven durante la ventana.

Esta función resuelve los tres: serializa por IP con un advisory lock de
transacción, decide y escribe en el mismo statement, y solo inserta cuando la
petición está dentro del tope. La limpieza de lo que ya no cuenta va en la misma
llamada, que es más barato que un cron para una tabla de este tamaño.

La invoca únicamente el cliente de servicio de Astro (el formulario es anónimo,
no hay sesión sobre la que apoyar RLS). `anon` y `authenticated` no reciben
EXECUTE: la 0018 cerró el default de funciones del esquema, y acá se otorga
explícitamente solo a `service_role`.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FIRMA = "public.registrar_solicitud_contacto(text, interval, integer)"

# Devuelve true cuando la solicitud supera el tope (y entonces no deja rastro).
# El advisory lock se toma sobre el hash de la IP y se libera al terminar la
# transacción: dos peticiones de la misma IP se serializan, y dos de IPs
# distintas no se estorban.
_FUNCION = """
CREATE OR REPLACE FUNCTION public.registrar_solicitud_contacto(
  p_ip_hash text,
  p_ventana interval,
  p_tope integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
DECLARE
  v_total integer;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(p_ip_hash));

  SELECT count(*) INTO v_total
    FROM public.contacto_solicitudes
   WHERE ip_hash = p_ip_hash
     AND creado_en >= now() - p_ventana;

  IF v_total >= p_tope THEN
    RETURN true;
  END IF;

  INSERT INTO public.contacto_solicitudes (ip_hash) VALUES (p_ip_hash);

  -- Una fila fuera de la ventana más larga imaginable ya no cuenta para nada.
  DELETE FROM public.contacto_solicitudes WHERE creado_en < now() - interval '24 hours';

  RETURN false;
END;
$fn$
"""


def upgrade() -> None:
    op.execute(_FUNCION)
    op.execute(f"REVOKE ALL ON FUNCTION {_FIRMA} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FIRMA} TO service_role")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_FIRMA}")
