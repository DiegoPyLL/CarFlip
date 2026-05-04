"""
Facebook Marketplace — Playwright async + playwright-stealth.
Requiere credenciales (email + password) para acceder a los listings.
Las cookies de sesión se reutilizan entre scrapes para evitar logins frecuentes.
"""

import re
from decimal import Decimal, InvalidOperation

from loguru import logger
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from sqlalchemy.ext.asyncio import AsyncSession

from carflipper import credentials
from carflipper.scrapers.base import BaseScraper, CarListing

LOGIN_URL = "https://www.facebook.com/login"
MARKETPLACE_URL = "https://www.facebook.com/marketplace/santiago/vehicles"
MAX_SCROLLS = 15


class FacebookScraper(BaseScraper):
    source = "facebook"

    def __init__(self, session: AsyncSession):
        self._db_session = session

    async def run(self, session: AsyncSession) -> object:
        self._db_session = session
        return await super().run(session)

    async def scrape(self) -> list[CarListing]:
        creds = credentials.get_credentials("facebook")
        if not creds:
            logger.warning("[facebook] Sin credenciales configuradas — omitiendo. "
                           "Ejecuta: carflipper credentials set facebook email password")
            return []

        email, password = creds
        listings: list[CarListing] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                locale="es-CL",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            await stealth_async(page)

            # Intentar restaurar cookies de sesión guardadas
            saved_cookies = await credentials.load_cookies(self._db_session, "facebook")
            if saved_cookies:
                await context.add_cookies(saved_cookies)
                logger.debug("[facebook] Cookies de sesión restauradas")
            else:
                await self._login(page, email, password)
                new_cookies = await context.cookies()
                await credentials.save_cookies(self._db_session, "facebook", new_cookies)

            try:
                await page.goto(MARKETPLACE_URL, wait_until="domcontentloaded", timeout=30000)
                # Scroll para cargar más resultados
                for _ in range(MAX_SCROLLS):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await self.random_delay()

                cards = await page.query_selector_all("[data-testid='marketplace_feed_item'], div[role='listitem']")
                logger.info(f"[facebook] {len(cards)} cards encontradas")

                for card in cards:
                    listing = await self._parse_card(card)
                    if listing:
                        listings.append(listing)

            except Exception as exc:
                logger.error(f"[facebook] Error scrapeando marketplace: {exc}")

            await browser.close()

        return listings

    async def _login(self, page, email: str, password: str) -> None:
        logger.info("[facebook] Iniciando sesión")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await page.fill("#email", email)
        await page.fill("#pass", password)
        await page.click("[name='login']")
        await page.wait_for_load_state("networkidle", timeout=15000)
        logger.info("[facebook] Sesión iniciada")

    async def _parse_card(self, card) -> CarListing | None:
        try:
            link = await card.query_selector("a[href*='/marketplace/item/']")
            if not link:
                return None
            href = await link.get_attribute("href") or ""
            url = f"https://www.facebook.com{href}" if href.startswith("/") else href
            id_match = re.search(r"/item/(\d+)", href)
            external_id = id_match.group(1) if id_match else re.sub(r"[^a-zA-Z0-9]", "_", href)[-80:]

            full_text = await card.inner_text()
            title_el = await card.query_selector("span[dir='auto'], div[class*='title']")
            title = (await title_el.inner_text()).strip() if title_el else full_text[:80]

            price = _parse_price(full_text)
            year_match = re.search(r"\b(19|20)\d{2}\b", full_text)
            year = int(year_match.group()) if year_match else None
            km_match = re.search(r"([\d.,]+)\s*km", full_text, re.IGNORECASE)
            km = int(re.sub(r"[^\d]", "", km_match.group(1))) if km_match else None

            return CarListing(
                source=self.source,
                external_id=external_id,
                url=url,
                title=title,
                price=price,
                year=year,
                km=km,
                location="Santiago",
            )
        except Exception as exc:
            logger.debug(f"[facebook] Error parseando card: {exc}")
            return None


def _parse_price(text: str) -> Decimal | None:
    match = re.search(r"[\$CLP\s]*([\d.,]+)", text)
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    try:
        return Decimal(digits) if digits else None
    except InvalidOperation:
        return None
