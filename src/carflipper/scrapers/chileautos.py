"""
Chileautos.cl — scraping con httpx + BeautifulSoup4.
"""

import re
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from loguru import logger

from carflipper.scrapers.base import BaseScraper, CarListing

BASE_URL = "https://www.chileautos.cl"
SEARCH_URL = f"{BASE_URL}/vehiculos/autos"
MAX_PAGES = 30
ua = UserAgent()


class ChileautosScraper(BaseScraper):
    source = "chileautos"

    async def scrape(self) -> list[CarListing]:
        listings: list[CarListing] = []
        async with httpx.AsyncClient(
            headers={"User-Agent": ua.random, "Accept-Language": "es-CL,es;q=0.9"},
            follow_redirects=True,
            timeout=30,
        ) as client:
            for page in range(1, MAX_PAGES + 1):
                params = {"Pagina": page}
                try:
                    resp = await client.get(SEARCH_URL, params=params)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.error(f"[chileautos] Error en página {page}: {exc}")
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                cards = soup.select(".listing-item, .car-listing, article[data-webm-vr]")
                if not cards:
                    logger.info(f"[chileautos] Sin resultados en página {page}, fin")
                    break

                for card in cards:
                    listing = self._parse_card(card)
                    if listing:
                        listings.append(listing)

                await self.random_delay()

        return listings

    def _parse_card(self, card) -> CarListing | None:
        try:
            link_tag = card.select_one("a[href]")
            if not link_tag:
                return None
            path = link_tag["href"]
            url = path if path.startswith("http") else f"{BASE_URL}{path}"
            external_id = re.sub(r"[^a-zA-Z0-9]", "_", path.strip("/"))[-80:]

            title_tag = card.select_one("h2, h3, .title, [class*='title']")
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

            price_tag = card.select_one("[class*='price'], .precio")
            price = _parse_price(price_tag.get_text(strip=True) if price_tag else "")

            year_match = re.search(r"\b(19|20)\d{2}\b", title + " " + card.get_text()[:300])
            year = int(year_match.group()) if year_match else None

            km_tag = card.select_one("[class*='km'], [class*='mileage']")
            km = _parse_km(km_tag.get_text(strip=True) if km_tag else "")

            location_tag = card.select_one("[class*='location'], [class*='region']")
            location = location_tag.get_text(strip=True) if location_tag else None

            return CarListing(
                source=self.source,
                external_id=external_id,
                url=url,
                title=title,
                price=price,
                year=year,
                km=km,
                location=location,
            )
        except Exception as exc:
            logger.debug(f"[chileautos] Error parseando card: {exc}")
            return None


def _parse_price(text: str) -> Decimal | None:
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _parse_km(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    try:
        return int(digits) if digits else None
    except ValueError:
        return None
