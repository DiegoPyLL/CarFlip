import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ListingMixin:
    """Columnas compartidas por todas las tablas de avisos."""

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_externo: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    precio: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True, index=True)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, server_default="CLP")
    marca: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    combustible: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Normalizadas al escribir (TRANSMISIONES / TRACCIONES en
    # web/src/lib/publicaciones/opciones.ts): valores canónicos o NULL, nunca
    # texto libre.
    transmision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    traccion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_imagen: Mapped[str | None] = mapped_column(Text, nullable=True)
    disponible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fecha_publicacion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    precio_anterior: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    primera_vez_visto: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultima_vez_visto: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Avisos scrapeados (congelados) ----------------------------------------
# Las cinco tablas que llenaba el pipeline de scraping, retirado en la 0022.
# Nadie las escribe ni las lee: se conservan con sus datos como registro de esa
# etapa, y sus modelos siguen declarados acá porque Alembic compara este
# metadata contra la base — borrarlos haría que el próximo --autogenerate
# propusiera un DROP de tablas que sí queremos mantener.


class AutocosmosListing(ListingMixin, Base):
    __tablename__ = "autocosmos_listings"


class MercadoLibreListing(ListingMixin, Base):
    __tablename__ = "mercadolibre_listings"


class YapoListing(ListingMixin, Base):
    __tablename__ = "yapo_listings"


class AutosusadosListing(ListingMixin, Base):
    __tablename__ = "autosusados_listings"


class CheckeadosListing(ListingMixin, Base):
    __tablename__ = "checkeados_listings"


# --- Deals y mercado --------------------------------------------------------


class Deal(Base):
    """Oportunidad de compra detectada por candidatos.sql y categorizada por IA (Groq).

    Guarda un snapshot del aviso al momento de la detección + contexto de mercado
    (mediana del grupo comparable marca/modelo/año) + la evaluación del LLM.
    """

    __tablename__ = "deals"
    __table_args__ = (UniqueConstraint("fuente", "id_externo", name="uq_deals_fuente_id_externo"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Snapshot del aviso
    fuente: Mapped[str] = mapped_column(String(50), nullable=False)
    id_externo: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    marca: Mapped[str | None] = mapped_column(String(100), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transmision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    traccion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    precio: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, server_default="CLP")
    url_imagen: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contexto de mercado (calculado por candidatos.sql)
    precio_mercado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    pct_vs_mercado: Mapped[float | None] = mapped_column(Float, nullable=True)  # negativo = barato
    delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparables: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Evaluación IA
    categoria: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    puntaje: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    riesgos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    resumen: Mapped[str | None] = mapped_column(Text, nullable=True)
    modelo_ia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    categorizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    precio_al_categorizar: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Estado
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketSnapshot(Base):
    """Agregado diario del mercado: una fila por día para las tendencias de /mercado.

    La escribe `snapshot_market()`, con upsert idempotente sobre `fecha`:
    re-correr el workflow el mismo día actualiza la fila, no la duplica.
    Recupera la serie temporal que se perdió al eliminar price_history en 0002,
    pero a nivel de mercado, no por aviso. `payload` guarda el detalle del día
    (histograma, top marcas, mix de combustible) como JSONB para poder graficar
    histórico más rico a futuro sin cambiar el esquema.

    Las filas anteriores a la 0022 agregan también los avisos scrapeados: son el
    registro de lo que hubo, así que no se recalculan.
    """

    __tablename__ = "market_snapshots"

    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    precio_promedio: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    precio_mediano: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    precio_p25: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    precio_p75: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    nuevos_24h: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    con_baja: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    por_fuente: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Avisos de particulares -------------------------------------------------
# Tablas escritas desde la web (Astro) con la anon key y protegidas por RLS, no
# por el pipeline Python. Viven aquí para que Alembic siga siendo la única
# fuente del esquema. La FK de perfiles.id contra auth.users la pone la
# migración: auth es un esquema de Supabase, fuera de este metadata.


class Perfil(Base):
    """Datos públicos y de contacto del usuario, 1:1 con auth.users.

    Las filas las crea un trigger AFTER INSERT sobre auth.users, así que un
    usuario recién registrado siempre tiene perfil. El rol de administrador NO
    vive aquí: está en app_metadata del JWT, que solo escribe el servidor de
    Supabase y no cuesta una consulta por request.
    """

    __tablename__ = "perfiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    nombre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comuna: Mapped[str | None] = mapped_column(String(100), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParticularListing(ListingMixin, Base):
    """Aviso publicado por un particular: quinta fuente de avisos.

    Reproduce ListingMixin tal cual para que la capa de lectura de la web
    (mapearAviso, aplicarFiltros, aplicarOrden) y candidatos.sql funcionen sin
    adaptadores. Las convenciones que lo hacen posible:

    - id_externo        uuid generado, cumple el unique heredado
    - url               URL canónica propia (https://carflip.cl/auto/p/<id>)
    - url_imagen        foto de portada
    - disponible        estado == 'publicado'
    - primera_vez_visto publicado_en
    - ultima_vez_visto  actualizado_en

    visible_en_deals es el opt-out del dueño: con false el aviso sigue publicado
    pero candidatos.sql lo excluye de Deals (y del LLM).
    """

    __tablename__ = "particulares_listings"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perfiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default="publicado", index=True)
    visible_en_deals: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Canónica (mayúsculas, sin separadores): 6 caracteres un auto, 5 una moto.
    # Nullable porque los avisos previos a la exigencia no la tienen; el
    # formulario la exige desde la migración 0016.
    patente: Mapped[str | None] = mapped_column(String(6), nullable=True)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vistas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    publicado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParticularFoto(Base):
    """Foto de un aviso de particular, almacenada en Supabase Storage.

    `ruta` es la clave dentro del bucket (<usuario_id>/<aviso_id>/<uuid>.webp):
    se guarda aparte de la URL pública para poder borrar el objeto. `orden` 0
    es la portada, que se copia a listings.url_imagen.
    """

    __tablename__ = "particulares_fotos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aviso_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("particulares_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    ruta: Mapped[str] = mapped_column(Text, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContactoRevelacion(Base):
    """Auditoría de cada vez que un usuario con sesión ve el teléfono de un aviso.

    Sostiene el tope anti-scraping de revelaciones por usuario y día, y le
    muestra al dueño del aviso cuánto interés recibió.
    """

    __tablename__ = "contacto_revelaciones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aviso_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("particulares_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perfiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ReporteAviso(Base):
    """Denuncia de un aviso: la moderación es reactiva, no hay revisión previa."""

    __tablename__ = "reportes_aviso"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aviso_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("particulares_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perfiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    motivo: Mapped[str] = mapped_column(String(50), nullable=False)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pendiente", index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
