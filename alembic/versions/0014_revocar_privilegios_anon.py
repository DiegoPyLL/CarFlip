"""Revocar los privilegios que Supabase otorga por defecto a anon y authenticated

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-23

Un proyecto Supabase trae configurado

    ALTER DEFAULT PRIVILEGES IN SCHEMA public
      GRANT ALL ON TABLES TO anon, authenticated, service_role

de modo que toda tabla creada en `public` nace con SELECT/INSERT/UPDATE/DELETE/
TRUNCATE para `anon`. Alembic corre como `postgres`, así que cada tabla de este
repo heredó ese ACL en el momento de crearse, y los GRANT selectivos de 0010
—pensados como el primer candado— quedaron como no-ops decorativos sobre
permisos que ya estaban todos dados.

El efecto en producción, verificado contra la API pública con la anon key:

    DELETE /rest/v1/autocosmos_listings  -> 204
    GET    /rest/v1/scrape_runs          -> 206 (métricas internas del pipeline)
    GET    /rest/v1/alembic_version      -> 200 [{"version_num": "0011"}]

Las tablas scrapeadas no tienen RLS —nunca la necesitaron, porque se asumía que
solo el pipeline las tocaba— así que sobre ellas no hay segunda barrera: con la
anon key, que es pública por diseño y viaja al navegador, cualquiera podía
vaciar el catálogo. En las cinco tablas de particulares el daño estaba contenido
porque RLS sí está activa y las políticas filtran, pero igual sobraban permisos
(TRUNCATE, en particular, RLS no lo cubre).

La corrección es cerrar por defecto y volver a otorgar solo lo que la aplicación
usa de verdad. Lo que la web necesita de `anon`/`authenticated` es exactamente
lo que definió 0010, y nada más:

- Las lecturas públicas (avisos scrapeados, deals, mercado, dashboard) las hace
  Astro en el servidor con la SERVICE key (`web/src/lib/db/client.ts`), que
  bypassa RLS y no depende de estos grants. El sitio es `output: 'server'` y
  ningún bundle de cliente habla con Supabase.
- Las tablas de particulares las escribe el navegador con la sesión del usuario
  (anon key + JWT, `web/src/lib/auth/servidor.ts`): esas sí dependen de los
  grants, y son las que se restauran abajo.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLES = "anon, authenticated"

# Cierra la puerta para las tablas que ya existen y para las que vengan. Sin la
# línea de DEFAULT PRIVILEGES, la próxima migración que cree una tabla vuelve a
# abrir el agujero y este arreglo dura hasta el siguiente `create_table`.
#
# ALTER DEFAULT PRIVILEGES solo altera las del rol que ejecuta, aquí `postgres`.
# Alcanza para este repo porque todas las tablas de `public` son suyas, pero
# Supabase mantiene una segunda entrada a nombre de `supabase_admin` que no
# podemos tocar (`postgres` no es superusuario ni miembro de ese rol). Una tabla
# creada por `supabase_admin` —por ejemplo desde el panel— nacería abierta igual
# y hay que revocarla a mano.
_REVOCAR = [
    f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {_ROLES}",
    f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {_ROLES}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {_ROLES}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {_ROLES}",
]

# Los grants de 0010 y 0011, ahora sí sobre una base vacía. `perfiles` no
# aparece para `anon` a propósito: el teléfono no debe salir por la API pública.
_GRANTS_APLICACION = [
    "GRANT SELECT ON public.particulares_listings, public.particulares_fotos TO anon",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.particulares_listings, public.particulares_fotos TO authenticated",
    "GRANT SELECT, UPDATE ON public.perfiles TO authenticated",
    "GRANT SELECT, INSERT ON public.contacto_revelaciones, public.reportes_aviso TO authenticated",
    "GRANT UPDATE ON public.reportes_aviso TO authenticated",
    """GRANT USAGE ON SEQUENCE
         public.particulares_listings_id_seq,
         public.particulares_fotos_id_seq,
         public.contacto_revelaciones_id_seq,
         public.reportes_aviso_id_seq
       TO authenticated""",
]


def upgrade() -> None:
    for sentencia in _REVOCAR:
        op.execute(sentencia)
    for sentencia in _GRANTS_APLICACION:
        op.execute(sentencia)


def downgrade() -> None:
    """Restaura el estado permisivo anterior.

    Existe para poder revertir la migración, no porque el estado previo sea
    defendible: deja otra vez el catálogo entero borrable con la anon key. Si
    algo se rompe tras el upgrade, es preferible otorgar el permiso puntual que
    falte antes que correr esto.
    """
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {_ROLES}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {_ROLES}")
    op.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {_ROLES}")
    op.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {_ROLES}")
