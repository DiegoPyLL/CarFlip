"""Quita el tope de avisos activos y sube el diario a 15

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-27

`particulares_topes` (0018) aplicaba dos topes: 5 avisos publicados a la vez y
3 creaciones por 24 h. El primero ya no corresponde: un usuario puede tener
publicados los avisos que quiera. El segundo sigue siendo la barrera contra un
alta masiva automatizada, pero 3 por día resultaba bajo para el uso real, así
que sube a 15.

`particulares_deriva_campos`, los CHECK de dominio, el GRANT por columna y los
UNIQUE de revelaciones/reportes no cambian: siguen siendo la frontera de
confianza para todo lo demás.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLA = "public.particulares_listings"

_FUNCION_NUEVA = """
CREATE OR REPLACE FUNCTION public.particulares_topes()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
BEGIN
  IF TG_OP = 'INSERT'
     AND (SELECT count(*) FROM public.particulares_listings
           WHERE usuario_id = NEW.usuario_id
             AND publicado_en >= now() - interval '24 hours') >= 15 THEN
    RAISE EXCEPTION 'tope_diario: 15 avisos creados por usuario en 24 horas'
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END;
$fn$
"""

_FUNCION_ANTERIOR = """
CREATE OR REPLACE FUNCTION public.particulares_topes()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
BEGIN
  IF NEW.estado = 'publicado'
     AND (SELECT count(*) FROM public.particulares_listings
           WHERE usuario_id = NEW.usuario_id
             AND estado = 'publicado'
             AND id <> NEW.id) >= 5 THEN
    RAISE EXCEPTION 'tope_activos: 5 avisos publicados por usuario'
      USING ERRCODE = 'check_violation';
  END IF;

  IF TG_OP = 'INSERT'
     AND (SELECT count(*) FROM public.particulares_listings
           WHERE usuario_id = NEW.usuario_id
             AND publicado_en >= now() - interval '24 hours') >= 3 THEN
    RAISE EXCEPTION 'tope_diario: 3 avisos creados por usuario en 24 horas'
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END;
$fn$
"""

# El trigger seguía disparándose en UPDATE OF estado para el tope de activos,
# que ya no existe: ahora solo importa el INSERT, así que se recrea acotado a eso.
_TRIGGER_ANTERIOR = f"""
CREATE TRIGGER particulares_topes
BEFORE INSERT OR UPDATE OF estado ON {_TABLA}
FOR EACH ROW EXECUTE FUNCTION public.particulares_topes()
"""

_TRIGGER_NUEVO = f"""
CREATE TRIGGER particulares_topes
BEFORE INSERT ON {_TABLA}
FOR EACH ROW EXECUTE FUNCTION public.particulares_topes()
"""


def upgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS particulares_topes ON {_TABLA}")
    op.execute(_FUNCION_NUEVA)
    op.execute(_TRIGGER_NUEVO)


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS particulares_topes ON {_TABLA}")
    op.execute(_FUNCION_ANTERIOR)
    op.execute(_TRIGGER_ANTERIOR)
