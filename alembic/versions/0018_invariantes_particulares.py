"""Invariantes de los avisos de particulares en la base, no solo en la aplicación

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-26

Hasta acá toda la validación de un aviso de particular vivía únicamente en la web
(`formulario.ts`, `limites.ts`, `api/publicacion/index.ts`). La 0010 otorgó
`INSERT, UPDATE` de tabla completa a `authenticated` y su única política de
escritura comprueba `usuario_id = auth.uid()`, así que con la anon key —pública
por diseño— y el JWT de una cuenta propia se podía hacer `POST` directo a
`/rest/v1/particulares_listings` y saltarse todo: avisos ilimitados, `titulo` y
`estado` de texto libre, precios negativos, `vistas` autoasignadas y
`ultima_vez_visto` en el futuro (la clave del orden "reciente" de /avisos, o sea
el primer puesto del listado a voluntad).

La corrección va donde está la frontera de confianza real:

- CHECK sobre los dominios de valor (estado, precio, km, año, largos, patente).
- GRANT por columna: lo que la web no escribe, `authenticated` no puede escribir.
  `vistas`, `publicado_en` (sostiene el tope de 3/24 h), `ultima_vez_visto`,
  `moneda`, `fecha_publicacion` y `url` quedan fuera de su alcance.
- Un trigger que *deriva* los campos que no son del usuario aunque los mande
  (titulo, url, disponible, marcas de tiempo, precio_anterior/delta_pct).
- Un trigger que aplica los topes de 5 activos y 3 creaciones por 24 h.
- UNIQUE en revelaciones y reportes: el "una vez por aviso" que hoy solo
  comprueba la aplicación, con la carrera que eso implica.

El trigger de derivación es deliberadamente tolerante: sobreescribe el valor que
llegue en vez de rechazarlo, y los GRANT por columna incluyen todo lo que la web
escribe hoy. Así esta migración se puede aplicar antes o después del deploy de la
web, en cualquier orden, sin dejar la publicación rota en el intervalo.

Los topes (5 y 3) duplican `LIMITES` de `web/src/lib/publicaciones/limites.ts`.
Es duplicación inevitable al cruzar de lenguaje: la aplicación sigue siendo la que
comprueba primero y da el mensaje bueno; esto es la red que la respalda.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLA = "public.particulares_listings"

# --- Dominios de valor ------------------------------------------------------
# Los límites numéricos son los de `formulario.ts` (KM_MAXIMO, PRECIO_MAXIMO).
# El techo del año es estático y holgado a propósito: un CHECK no admite
# expresiones no inmutables como now(), así que el "año actual + 1" exacto lo
# sigue validando `anioMaximo()`. La patente se comprueba en su forma canónica
# (mayúsculas, sin separadores), que es lo que produce `normalizarPatente`; los
# cuatro formatos legales los valida la web, acá basta con cerrar el texto libre.
_CHECKS = {
    "ck_particulares_estado": "estado IN ('publicado', 'pausado', 'vendido')",
    "ck_particulares_precio": "precio IS NULL OR (precio > 0 AND precio <= 999000000)",
    "ck_particulares_km": "km IS NULL OR (km >= 0 AND km <= 2000000)",
    "ck_particulares_anio": "anio IS NULL OR (anio >= 1950 AND anio <= 2100)",
    "ck_particulares_vistas": "vistas >= 0",
    "ck_particulares_titulo_largo": "char_length(titulo) <= 200",
    "ck_particulares_descripcion_largo": "descripcion IS NULL OR char_length(descripcion) <= 2000",
    "ck_particulares_patente": "patente IS NULL OR patente ~ '^[A-Z0-9]{5,6}$'",
}

# --- Privilegios por columna ------------------------------------------------
# PostgreSQL no tiene "GRANT todas menos estas": hay que revocar el privilegio de
# tabla y volver a otorgarlo columna por columna. La lista es exactamente lo que
# escribe la web; lo que falta acá no es escribible ni por PostgREST ni por nadie
# con el rol `authenticated`.
_COLUMNAS_COMUNES = [
    "titulo",
    "marca",
    "modelo",
    "version",
    "anio",
    "km",
    "precio",
    "patente",
    "combustible",
    "transmision",
    "traccion",
    "ubicacion",
    "descripcion",
    "url_imagen",
    "visible_en_deals",
    "estado",
    "disponible",
]
# `url`, `titulo`, `precio_anterior`, `delta_pct` y las marcas de tiempo siguen
# otorgadas porque la web las manda hoy: el trigger las sobreescribe, así que
# otorgarlas no le da control sobre ellas y evita que esta migración tenga que
# desplegarse en un orden concreto respecto de la web.
_COLUMNAS_INSERT = [*_COLUMNAS_COMUNES, "id_externo", "usuario_id", "url"]
_COLUMNAS_UPDATE = [
    *_COLUMNAS_COMUNES,
    "precio_anterior",
    "delta_pct",
    "actualizado_en",
    "ultima_vez_visto",
]

_GRANTS_COLUMNA = [
    f"REVOKE INSERT, UPDATE ON {_TABLA} FROM authenticated",
    f"GRANT INSERT ({', '.join(_COLUMNAS_INSERT)}) ON {_TABLA} TO authenticated",
    f"GRANT UPDATE ({', '.join(_COLUMNAS_UPDATE)}) ON {_TABLA} TO authenticated",
]

# --- Derivación de los campos que no son del usuario ------------------------
# SECURITY DEFINER con search_path vacío y nombres calificados, igual que
# `crear_perfil_para_usuario` en la 0010.
#
# `titulo` se arma desde marca/modelo/versión/año: es lo que hace el formulario y
# lo que impide que sea texto libre indexable. `url` necesita el id, que en un
# BEFORE INSERT ya viene asignado por la secuencia, así que la web deja de
# necesitar un segundo UPDATE para escribirla. `disponible` es la lectura
# genérica de `estado` para el resto del sitio: nunca deben desincronizarse.
_FUNCION_NORMALIZA = """
CREATE OR REPLACE FUNCTION public.particulares_deriva_campos()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
BEGIN
  NEW.titulo := btrim(concat_ws(' ', NEW.marca, NEW.modelo, NEW.version, NEW.anio));
  NEW.url := 'https://carflip.cl/auto/p/' || NEW.id;
  NEW.disponible := (NEW.estado = 'publicado');
  NEW.actualizado_en := now();

  IF TG_OP = 'INSERT' THEN
    NEW.precio_anterior := NULL;
    NEW.delta_pct := NULL;
    RETURN NEW;
  END IF;

  NEW.ultima_vez_visto := now();
  NEW.vistas := OLD.vistas;
  NEW.publicado_en := OLD.publicado_en;
  NEW.primera_vez_visto := OLD.primera_vez_visto;

  -- Una bajada de precio alimenta el "▼ n%" del listado y el snapshot de deals,
  -- así que la calcula la base y no quien manda el UPDATE.
  NEW.precio_anterior := OLD.precio_anterior;
  NEW.delta_pct := OLD.delta_pct;
  IF NEW.precio IS NOT NULL AND OLD.precio > 0 AND NEW.precio < OLD.precio THEN
    NEW.precio_anterior := OLD.precio;
    NEW.delta_pct := ((NEW.precio - OLD.precio) / OLD.precio) * 100;
  END IF;

  RETURN NEW;
END;
$fn$
"""

_TRIGGER_NORMALIZA = f"""
CREATE TRIGGER particulares_deriva_campos
BEFORE INSERT OR UPDATE ON {_TABLA}
FOR EACH ROW EXECUTE FUNCTION public.particulares_deriva_campos()
"""

# --- Topes anti-abuso -------------------------------------------------------
# Republicar un aviso pausado cuenta contra el tope de activos: si no, pausar y
# republicar en bucle sería la vuelta fácil al límite, igual que razona estado.ts.
_FUNCION_TOPES = """
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

# Se dispara al crear y al volver a publicar; un UPDATE que no cambia el estado no
# tiene por qué pagar dos conteos.
_TRIGGER_TOPES = f"""
CREATE TRIGGER particulares_topes
BEFORE INSERT OR UPDATE OF estado ON {_TABLA}
FOR EACH ROW EXECUTE FUNCTION public.particulares_topes()
"""

# --- Unicidad de revelaciones y reportes ------------------------------------
# `yaReveloContacto` y `yaReportoAviso` comprueban antes de insertar, pero eso es
# una carrera: dos requests en paralelo pasan las dos. Y por PostgREST directo no
# hay comprobación ninguna.
_UNIQUES = [
    (
        "public.contacto_revelaciones",
        "uq_contacto_revelaciones_aviso_usuario",
        "aviso_id, usuario_id",
    ),
    ("public.reportes_aviso", "uq_reportes_aviso_aviso_usuario", "aviso_id, usuario_id"),
]

# --- Funciones cerradas por defecto ----------------------------------------
# La 0014 cerró las tablas y las secuencias de `public`, pero no las funciones, y
# ahí pasa lo mismo: Supabase trae
#
#     ALTER DEFAULT PRIVILEGES IN SCHEMA public
#       GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role
#
# así que toda función de este repo nació con EXECUTE explícito para `anon`, que
# es pública por diseño. Verificado en la base: `crear_perfil_para_usuario` (0010)
# tenía `anon=X/postgres`. Eso deja invocable por PostgREST cualquier función del
# esquema, incluidas las SECURITY DEFINER, que existen justamente para saltarse
# RLS. Se revoca sobre las que existen y se cierra el default para las que vengan.
#
# Va al final del upgrade a propósito: así alcanza también a las dos funciones que
# crea esta misma migración. El REVOKE a PUBLIC no es redundante —cubre el default
# de PostgreSQL, distinto del de Supabase— y ninguno de los dos toca a
# `service_role`, que es quien las necesita.
_CIERRE_FUNCIONES = [
    "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated",
    "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated",
]


def upgrade() -> None:
    for nombre, condicion in _CHECKS.items():
        op.execute(f"ALTER TABLE {_TABLA} ADD CONSTRAINT {nombre} CHECK ({condicion})")

    for tabla, nombre, columnas in _UNIQUES:
        op.execute(f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} UNIQUE ({columnas})")

    op.execute(_FUNCION_NORMALIZA)
    op.execute(_TRIGGER_NORMALIZA)
    op.execute(_FUNCION_TOPES)
    op.execute(_TRIGGER_TOPES)

    for sentencia in _GRANTS_COLUMNA:
        op.execute(sentencia)

    for sentencia in _CIERRE_FUNCIONES:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated")
    op.execute("GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated")

    op.execute(f"REVOKE INSERT, UPDATE ON {_TABLA} FROM authenticated")
    op.execute(f"GRANT INSERT, UPDATE ON {_TABLA} TO authenticated")

    op.execute(f"DROP TRIGGER IF EXISTS particulares_topes ON {_TABLA}")
    op.execute("DROP FUNCTION IF EXISTS public.particulares_topes()")
    op.execute(f"DROP TRIGGER IF EXISTS particulares_deriva_campos ON {_TABLA}")
    op.execute("DROP FUNCTION IF EXISTS public.particulares_deriva_campos()")

    for tabla, nombre, _ in _UNIQUES:
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {nombre}")

    for nombre in _CHECKS:
        op.execute(f"ALTER TABLE {_TABLA} DROP CONSTRAINT IF EXISTS {nombre}")
