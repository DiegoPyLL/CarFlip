import asyncio
import hashlib
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.config import settings


@dataclass
class AvisoAuto:
    """Datos normalizados de un aviso de auto."""

    fuente: str
    id_externo: str
    url: str
    titulo: str
    precio: Decimal | None = None
    moneda: str = "CLP"
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    km: int | None = None
    ubicacion: str | None = None
    combustible: str | None = None
    descripcion: str | None = None
    url_imagen: str | None = None
    disponible: bool | None = None
    fecha_publicacion: str | None = None

    @property
    def nombre_normalizado(self) -> str:
        def slug(s: str) -> str:
            return re.sub(r"[^\w]", "_", s.lower()).strip("_")

        url_hash = hashlib.sha256(self.url.encode()).hexdigest()[:8]
        partes = [self.fuente]
        if self.marca:
            partes.append(slug(self.marca))
        if self.modelo:
            partes.append(slug(self.modelo))
        if self.anio:
            partes.append(str(self.anio))
        partes.append(url_hash)
        return "_".join(partes)


@dataclass
class ResultadoScraping:
    fuente: str
    iniciado_en: datetime = field(default_factory=datetime.now)
    finalizado_en: datetime | None = None
    avisos: list[AvisoAuto] = field(default_factory=list)
    errores: int = 0


class ScraperBase(ABC):
    fuente: str = ""
    model_class: type | None = None  # tabla Supabase destino, declarada en cada scraper

    async def ejecutar(self, sesion: AsyncSession) -> ResultadoScraping:
        from carflip.database.uploader import upsert_avisos

        resultado = ResultadoScraping(fuente=self.fuente)
        logger.info(f"[{self.fuente}] Iniciando scraping")
        try:
            avisos = await self.scrape()
            resultado.avisos = avisos
            logger.info(f"[{self.fuente}] {len(avisos)} avisos obtenidos")

            if avisos and self.model_class is not None:
                n = await upsert_avisos(sesion, avisos, self.model_class)
                logger.info(f"[{self.fuente}] {n} avisos subidos a Supabase ({self.model_class.__tablename__})")
        except Exception as exc:
            resultado.errores += 1
            logger.error(f"[{self.fuente}] Error fatal: {exc}")
        resultado.finalizado_en = datetime.now()
        return resultado

    @abstractmethod
    async def scrape(self) -> list[AvisoAuto]:
        """Implementar la lógica de scraping de cada sitio."""

    async def espera_aleatoria(self) -> None:
        espera = random.uniform(settings.min_delay_seconds, settings.max_delay_seconds)
        await asyncio.sleep(espera)
