import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from carflipper.config import settings


@dataclass
class CarListing:
    """Datos normalizados de un aviso de auto."""

    source: str
    external_id: str
    url: str
    title: str
    price: Decimal | None = None
    currency: str = "CLP"
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    km: int | None = None
    location: str | None = None


@dataclass
class ScrapeResult:
    source: str
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    listings: list[CarListing] = field(default_factory=list)
    errors: int = 0


class BaseScraper(ABC):
    source: str = ""

    async def run(self, session: AsyncSession) -> ScrapeResult:
        result = ScrapeResult(source=self.source)
        logger.info(f"[{self.source}] Iniciando scraping")
        try:
            listings = await self.scrape()
            result.listings = listings
            logger.info(f"[{self.source}] {len(listings)} avisos obtenidos")
        except Exception as exc:
            result.errors += 1
            logger.error(f"[{self.source}] Error fatal: {exc}")
        result.finished_at = datetime.now()
        return result

    @abstractmethod
    async def scrape(self) -> list[CarListing]:
        """Implementar la lógica de scraping de cada sitio."""

    async def random_delay(self) -> None:
        delay = random.uniform(settings.min_delay_seconds, settings.max_delay_seconds)
        await asyncio.sleep(delay)
