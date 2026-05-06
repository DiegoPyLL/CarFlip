"""
MercadoLibre Chile — usa la API oficial pública (no requiere autenticación para búsquedas).
Documentación: https://developers.mercadolibre.cl/es_ar/items-y-busquedas
"""

from decimal import Decimal

import httpx
from loguru import logger

from carflip.scrapers.base import BaseScraper, CarListing

SITE_ID = "MLC"
API_BASE = "https://api.mercadolibre.com"
CATEGORY_AUTOS = "MLC1747"  # Autos y Camionetas
MAX_PAGES = 20
PAGE_SIZE = 50


class MercadoLibreScraper(BaseScraper):
    source = "mercadolibre"

    async def scrape(self) -> list[CarListing]:
        listings: list[CarListing] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for offset in range(0, MAX_PAGES * PAGE_SIZE, PAGE_SIZE):
                url = f"{API_BASE}/sites/{SITE_ID}/search"
                params = {"category": CATEGORY_AUTOS, "offset": offset, "limit": PAGE_SIZE}
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPError as exc:
                    logger.error(f"[mercadolibre] HTTP error en offset {offset}: {exc}")
                    break

                results = data.get("results", [])
                if not results:
                    break

                for item in results:
                    listings.append(self._parse_item(item))

                await self.random_delay()

        return listings

    def _parse_item(self, item: dict) -> CarListing:
        attrs = {a["id"]: a.get("value_name") for a in item.get("attributes", [])}
        price_raw = item.get("price")
        price = Decimal(str(price_raw)) if price_raw else None

        km_raw = attrs.get("VEHICLE_MILEAGE") or attrs.get("KILOMETERS")
        try:
            km = int(km_raw.replace(".", "").replace(",", "")) if km_raw else None
        except (ValueError, AttributeError):
            km = None

        year_raw = attrs.get("VEHICLE_YEAR")
        try:
            year = int(year_raw) if year_raw else None
        except (ValueError, TypeError):
            year = None

        return CarListing(
            source=self.source,
            external_id=item["id"],
            url=item.get("permalink", ""),
            title=item.get("title", ""),
            price=price,
            currency=item.get("currency_id", "CLP"),
            brand=attrs.get("BRAND"),
            model=attrs.get("MODEL"),
            year=year,
            km=km,
            location=item.get("address", {}).get("city_name"),
        )
