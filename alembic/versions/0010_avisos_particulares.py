"""Avisos de particulares: perfiles, avisos propios, fotos, revelaciones y reportes

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-21

Convierte CarFlip de agregador de solo lectura en plataforma con contenido de
terceros: estas cinco tablas las escribe la web con la anon key del usuario, no
el pipeline Python, así que la autorización vive en políticas RLS y no en el
código de la aplicación.

particulares_listings reproduce ListingMixin tal cual para que la capa de
lectura de la web y candidatos.sql la traten como una fuente más.

Esta migración exige Supabase: usa el esquema `auth` (FK contra auth.users y el
trigger que crea el perfil), los roles `anon`/`authenticated` y las funciones
auth.uid()/auth.jwt() de las políticas. Contra un PostgreSQL pelado falla en el
primer statement, y así debe ser: crear estas tablas sin RLS las dejaría
legibles y escribibles por cualquiera a través de PostgREST.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLAS = [
    "reportes_aviso",
    "contacto_revelaciones",
    "particulares_fotos",
    "particulares_listings",
    "perfiles",
]

# --- Objetos de Supabase: trigger de perfil, grants y RLS -------------------
# Alembic no autogenera nada de esto; va a mano y en el mismo revision para que
# ninguna de las tablas llegue a existir sin sus políticas.

# El perfil es una extensión 1:1 de la cuenta: al borrar el usuario cae el
# perfil y, en cascada, sus avisos, fotos, revelaciones y reportes.
_FK_AUTH_USERS = """
ALTER TABLE public.perfiles
  ADD CONSTRAINT fk_perfiles_auth_users
  FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE
"""

# search_path vacío + nombres calificados: la función es SECURITY DEFINER, así
# no puede desviarse a un objeto homónimo de otro esquema.
_FUNCION_PERFIL = """
CREATE OR REPLACE FUNCTION public.crear_perfil_para_usuario()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
BEGIN
  INSERT INTO public.perfiles (id) VALUES (NEW.id) ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$fn$
"""

_TRIGGER_PERFIL = """
CREATE TRIGGER crear_perfil_al_registrarse
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.crear_perfil_para_usuario()
"""

# PostgREST no ve una tabla sin GRANT, aunque tenga políticas. `perfiles` no se
# otorga a anon: el teléfono no debe salir jamás por la API pública.
_GRANTS = [
    "GRANT SELECT ON public.particulares_listings, public.particulares_fotos TO anon",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.particulares_listings, public.particulares_fotos TO authenticated",
    "GRANT SELECT, UPDATE ON public.perfiles TO authenticated",
    "GRANT SELECT, INSERT ON public.contacto_revelaciones, public.reportes_aviso TO authenticated",
    """GRANT USAGE ON SEQUENCE
         public.particulares_listings_id_seq,
         public.particulares_fotos_id_seq,
         public.contacto_revelaciones_id_seq,
         public.reportes_aviso_id_seq
       TO authenticated""",
]

_POLITICAS = [
    # perfiles: cada quien ve y edita el suyo, nadie más. Sin lectura anónima.
    """CREATE POLICY perfiles_select_propio ON public.perfiles
         FOR SELECT TO authenticated USING (id = (SELECT auth.uid()))""",
    """CREATE POLICY perfiles_update_propio ON public.perfiles
         FOR UPDATE TO authenticated
         USING (id = (SELECT auth.uid()))
         WITH CHECK (id = (SELECT auth.uid()))""",
    # avisos: públicos si están publicados; el dueño ve además los pausados y
    # vendidos, que es lo que necesita "Mis publicaciones".
    """CREATE POLICY listings_select_publicados ON public.particulares_listings
         FOR SELECT TO anon, authenticated
         USING (estado = 'publicado' OR usuario_id = (SELECT auth.uid()))""",
    """CREATE POLICY listings_insert_propio ON public.particulares_listings
         FOR INSERT TO authenticated WITH CHECK (usuario_id = (SELECT auth.uid()))""",
    """CREATE POLICY listings_update_propio ON public.particulares_listings
         FOR UPDATE TO authenticated
         USING (usuario_id = (SELECT auth.uid()))
         WITH CHECK (usuario_id = (SELECT auth.uid()))""",
    """CREATE POLICY listings_delete_propio ON public.particulares_listings
         FOR DELETE TO authenticated USING (usuario_id = (SELECT auth.uid()))""",
    # fotos: heredan las reglas del aviso padre.
    """CREATE POLICY fotos_select_visibles ON public.particulares_fotos
         FOR SELECT TO anon, authenticated
         USING (EXISTS (
           SELECT 1 FROM public.particulares_listings l
           WHERE l.id = aviso_id
             AND (l.estado = 'publicado' OR l.usuario_id = (SELECT auth.uid()))
         ))""",
    """CREATE POLICY fotos_escribe_dueno ON public.particulares_fotos
         FOR ALL TO authenticated
         USING (EXISTS (
           SELECT 1 FROM public.particulares_listings l
           WHERE l.id = aviso_id AND l.usuario_id = (SELECT auth.uid())
         ))
         WITH CHECK (EXISTS (
           SELECT 1 FROM public.particulares_listings l
           WHERE l.id = aviso_id AND l.usuario_id = (SELECT auth.uid())
         ))""",
    # revelaciones: las lee el dueño del aviso (interés recibido) y quien las
    # generó, porque el tope de 20/día se cuenta con su propia sesión.
    """CREATE POLICY revelaciones_insert_propio ON public.contacto_revelaciones
         FOR INSERT TO authenticated WITH CHECK (usuario_id = (SELECT auth.uid()))""",
    """CREATE POLICY revelaciones_select_involucrados ON public.contacto_revelaciones
         FOR SELECT TO authenticated
         USING (
           usuario_id = (SELECT auth.uid())
           OR EXISTS (
             SELECT 1 FROM public.particulares_listings l
             WHERE l.id = aviso_id AND l.usuario_id = (SELECT auth.uid())
           )
         )""",
    # reportes: los crea cualquier autenticado y solo los lee un administrador.
    # El rol viaja en app_metadata del JWT, que únicamente escribe Supabase.
    """CREATE POLICY reportes_insert_autenticado ON public.reportes_aviso
         FOR INSERT TO authenticated WITH CHECK (usuario_id = (SELECT auth.uid()))""",
    """CREATE POLICY reportes_select_admin ON public.reportes_aviso
         FOR SELECT TO authenticated
         USING (((SELECT auth.jwt()) -> 'app_metadata' ->> 'rol') = 'admin')""",
]


def upgrade() -> None:
    op.create_table(
        "perfiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=True),
        sa.Column("telefono", sa.String(20), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("comuna", sa.String(100), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # Columnas de ListingMixin, idénticas a las de las tablas scrapeadas.
    op.create_table(
        "particulares_listings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_externo", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("precio", sa.Numeric(14, 2), nullable=True),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="CLP"),
        sa.Column("marca", sa.String(100), nullable=True),
        sa.Column("modelo", sa.String(100), nullable=True),
        sa.Column("anio", sa.Integer(), nullable=True),
        sa.Column("km", sa.Integer(), nullable=True),
        sa.Column("ubicacion", sa.String(200), nullable=True),
        sa.Column("combustible", sa.String(50), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("url_imagen", sa.Text(), nullable=True),
        sa.Column("disponible", sa.Boolean(), nullable=True),
        sa.Column("fecha_publicacion", sa.String(50), nullable=True),
        sa.Column("precio_anterior", sa.Numeric(14, 2), nullable=True),
        sa.Column("delta_pct", sa.Float(), nullable=True),
        sa.Column("primera_vez_visto", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ultima_vez_visto", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Propias del aviso de particular.
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="publicado"),
        sa.Column("transmision", sa.String(50), nullable=True),
        sa.Column("version", sa.String(100), nullable=True),
        sa.Column("vistas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publicado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_externo", name="uq_particulares_listings_id_externo"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["perfiles.id"],
            name="fk_particulares_listings_usuario",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_particulares_listings_precio", "particulares_listings", ["precio"])
    op.create_index("ix_particulares_listings_marca", "particulares_listings", ["marca"])
    op.create_index("ix_particulares_listings_modelo", "particulares_listings", ["modelo"])
    op.create_index("ix_particulares_listings_anio", "particulares_listings", ["anio"])
    op.create_index("ix_particulares_listings_usuario_id", "particulares_listings", ["usuario_id"])
    op.create_index("ix_particulares_listings_estado", "particulares_listings", ["estado"])

    op.create_table(
        "particulares_fotos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("aviso_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("ruta", sa.Text(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["aviso_id"],
            ["particulares_listings.id"],
            name="fk_particulares_fotos_aviso",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_particulares_fotos_aviso_id", "particulares_fotos", ["aviso_id"])

    op.create_table(
        "contacto_revelaciones",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("aviso_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["aviso_id"],
            ["particulares_listings.id"],
            name="fk_contacto_revelaciones_aviso",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["perfiles.id"],
            name="fk_contacto_revelaciones_usuario",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_contacto_revelaciones_aviso_id", "contacto_revelaciones", ["aviso_id"])
    op.create_index("ix_contacto_revelaciones_usuario_id", "contacto_revelaciones", ["usuario_id"])
    op.create_index("ix_contacto_revelaciones_creado_en", "contacto_revelaciones", ["creado_en"])

    op.create_table(
        "reportes_aviso",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("aviso_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("motivo", sa.String(50), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["aviso_id"],
            ["particulares_listings.id"],
            name="fk_reportes_aviso_aviso",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["perfiles.id"],
            name="fk_reportes_aviso_usuario",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_reportes_aviso_aviso_id", "reportes_aviso", ["aviso_id"])
    op.create_index("ix_reportes_aviso_usuario_id", "reportes_aviso", ["usuario_id"])
    op.create_index("ix_reportes_aviso_estado", "reportes_aviso", ["estado"])

    op.execute(_FK_AUTH_USERS)
    op.execute(_FUNCION_PERFIL)
    op.execute(_TRIGGER_PERFIL)

    for sentencia in _GRANTS:
        op.execute(sentencia)

    for tabla in _TABLAS:
        op.execute(f"ALTER TABLE public.{tabla} ENABLE ROW LEVEL SECURITY")

    for politica in _POLITICAS:
        op.execute(politica)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS crear_perfil_al_registrarse ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.crear_perfil_para_usuario()")
    # Las políticas y los grants caen junto con la tabla.
    for tabla in _TABLAS:
        op.drop_table(tabla)
