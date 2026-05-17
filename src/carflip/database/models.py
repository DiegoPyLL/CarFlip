from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, Numeric, String, Text, func
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


class ScrapedRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_found: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
