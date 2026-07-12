from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ListingMixin:
    """Columnas compartidas por todas las tablas de avisos por fuente."""

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
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_imagen: Mapped[str | None] = mapped_column(Text, nullable=True)
    disponible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fecha_publicacion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    precio_anterior: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    primera_vez_visto: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultima_vez_visto: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutocosmosListing(ListingMixin, Base):
    __tablename__ = "autocosmos_listings"


class MercadoLibreListing(ListingMixin, Base):
    __tablename__ = "mercadolibre_listings"


class YapoListing(ListingMixin, Base):
    __tablename__ = "yapo_listings"


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


class ScrapedRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_found: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
