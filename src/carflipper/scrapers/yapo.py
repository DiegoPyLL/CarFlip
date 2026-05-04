"""
Yapo.cl — Playwright async. Puede requerir login para ver datos de contacto.
"""

import re
from decimal import Decimal, InvalidOperation

from loguru import logger
from playwright.async_api import Browser, async_playwright

from carflipper.scrapers.base import BaseScraper, CarListing

BASE_URL = "https://www.yapo.cl"
SEARCH_URL = f"{BASE_URL}/region_metropolitana/autos"
MAX_PAGES = 20


class YapoScraper(BaseScraper):
    source = "yapo"

    async def scrape(self) -> list[CarListing]:
        listings: list[CarListing] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                locale="es-CL",
            )
            page = await context.new_page()

            for page_num in range(1, MAX_PAGES + 1):
                url = f"{SEARCH_URL}?o={page_num}"
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_selector("li.adsitem, .ad-item, article", timeout=10000)
                except Exception as exc:
                    logger.error(f"[yapo] Error en página {page_num}: {exc}")
                    break

                cards = await page.query_selector_all("li.adsitem, .ad-item, article.listing-ad")
                if not cards:
                    logger.info(f"[yapo] Sin avisos en página {page_num}, fin")
                    break

                for card in cards:
                    listing = await self._parse_card(card)
                    if listing:
                        listings.append(listing)

                await self.random_delay()

            await browser.close()

        return listings

    async def _parse_card(self, card) -> CarListing | None:
        try:
            link = await card.query_selector("a[href]")
            if not link:
                return None
            href = await link.get_attribute("href") or ""
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            external_id = re.sub(r"[^a-zA-Z0-9]", "_", href.strip("/"))[-80:]

            title_el = await card.query_selector("h2, h3, .title-ad, [class*='title']")
            title = await title_el.inner_text() if title_el else url

            price_el = await card.query_selector("[class*='price'], .price")
            price_text = await price_el.inner_text() if price_el else ""
            price = _parse_price(price_text)

            full_text = await card.inner_text()
            year_match = re.search(r"\b(19|20)\d{2}\b", full_text)
            year = int(year_match.group()) if year_match else None

            km_match = re.search(r"([\d.,]+)\s*km", full_text, re.IGNORECASE)
            km = int(re.sub(r"[^\d]", "", km_match.group(1))) if km_match else None

            return CarListing(
                source=self.source,
                external_id=external_id,
                url=url,
                title=title.strip(),
                price=price,
                year=year,
                km=km,
            )
        except Exception as exc:
            logger.debug(f"[yapo] Error parseando card: {exc}")
            return None


def _parse_price(text: str) -> Decimal | None:
    digits = re.sub(r"[^\d]", "", text)
    try:
        return Decimal(digits) if digits else None
    except InvalidOperation:
        return None
