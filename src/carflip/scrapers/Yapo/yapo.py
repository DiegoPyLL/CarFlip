import asyncio
import re
from datetime import datetime

from loguru import logger
from playwright.async_api import async_playwright

from carflip.database.models import YapoListing
from carflip.scrapers.base import AvisoAuto, ScraperBase


class ScraperYapo(ScraperBase):
    """Scraper básico asíncrono para Yapo. Extrae la información sin descargar fotos."""

    fuente = "yapo"
    model_class = YapoListing

    _JS_ATTRS = """() => {
        const dls = document.querySelectorAll('.d3-property-insight__attribute-details');
        const out = {};
        for (const dl of dls) {
            const dts = dl.querySelectorAll('dt');
            const dds = dl.querySelectorAll('dd');
            for (let i = 0; i < dts.length; i++) {
                out[dts[i].innerText.trim()] = dds[i] ? dds[i].innerText.trim() : '';
            }
        }
        for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
            try {
                const d = JSON.parse(s.textContent);
                if (d['@type'] === 'Car') {
                    if (d.vehicleTransmission && !out['Transmision']) out['Transmision'] = d.vehicleTransmission;
                    if (d.fuelType && !out['Combustible']) out['Combustible'] = d.fuelType;
                    if (d.mileageFromOdometer && !out['Kilometros']) out['Kilometros'] = String(d.mileageFromOdometer.value || '');
                    if (d.modelDate && !out['Ano']) out['Ano'] = String(d.modelDate);
                }
            } catch(e) {}
        }
        out['imagen_url'] = '';
        for (const img of document.querySelectorAll(
            '.d3-gallery img, .d3-photos-carousel img, [class*="gallery"] img, [class*="photo"] img'
        )) {
            const src = img.src || img.dataset.src || '';
            if (src && src.startsWith('http') && src.includes('t_or_fh')) {
                out['imagen_url'] = src;
                break;
            }
        }
        return out;
    }"""

    def _get_attr(self, attrs: dict, *claves: str) -> str:
        import unicodedata

        def norm(s: str) -> str:
            return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

        for clave in claves:
            for k, v in attrs.items():
                if norm(k) == norm(clave) and v:
                    return v
        return ""

    def _limpiar_km(self, texto: str) -> int | None:
        solo = re.sub(r"[.'`,\s]", "", texto)
        return int(solo) if solo.isdigit() else None

    def _limpiar_precio(self, texto: str) -> int | None:
        linea = texto.split("\n")[0]
        solo = re.sub(r"[^\d]", "", linea)
        return int(solo) if solo else None

    def _normalizar_combustible(self, valor: str) -> str | None:
        v = valor.lower().strip()
        if any(w in v for w in ["eléctrico", "electrico", "electric", "ev"]): return "electrico"
        if any(w in v for w in ["híbrido", "hibrido", "hybrid"]): return "hibrido"
        if any(w in v for w in ["diesel", "diésel"]): return "diesel"
        if any(w in v for w in ["bencina", "gasolina", "nafta"]): return "bencina"
        return v if v else None

    async def _recolectar_urls(self, page, max_paginas: int) -> list[dict]:
        base_url = "https://www.yapo.cl/region_metropolitana/autos"
        avisos = []

        for pagina in range(1, max_paginas + 1):
            url = f"{base_url}?o={pagina}" if pagina > 1 else base_url
            logger.info(f"[{self.fuente}] Listado página {pagina}: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_selector("div.d3-ads-grid", timeout=20_000)
            except Exception as e:
                logger.warning(f"[{self.fuente}] Timeout en página {pagina}: {e}")
                break

            await page.wait_for_timeout(2000)
            cards = await page.query_selector_all("div.d3-ad-tile")

            for card in cards:
                link = await card.query_selector("a[href^='/autos-usados']")
                if not link: continue
                href = await link.get_attribute("href")
                if not href: continue

                async def _safe(sel: str) -> str:
                    try:
                        n = await card.query_selector(sel)
                        return (await n.inner_text()).strip() if n else ""
                    except Exception:
                        return ""

                avisos.append({
                    "url": "https://www.yapo.cl" + href,
                    "precio": await _safe("[class*='d3-ad-tile__price']"),
                    "region": await _safe("[class*='d3-ad-tile__location']"),
                    "fecha": await _safe("time, [class*='date']") or datetime.now().strftime("%Y-%m-%d"),
                })
        return avisos

    async def _scrape_detalle(self, page, aviso_info: dict) -> AvisoAuto | None:
        url = aviso_info["url"]
        aviso_id = url.rstrip("/").split("/")[-1]

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            await page.wait_for_timeout(1500)
            attrs = await page.evaluate(self._JS_ATTRS)
        except Exception as e:
            logger.error(f"[{self.fuente}] Error cargando detalle {url}: {e}")
            return None

        km_raw = self._get_attr(attrs, "Kilómetros", "Kilometros", "Kilometraje")
        precio = self._limpiar_precio(aviso_info["precio"])
        km = self._limpiar_km(km_raw) if km_raw else None
        anio_s = self._get_attr(attrs, "Año", "Ano")
        anio = int(anio_s) if anio_s.isdigit() else None

        marca = self._get_attr(attrs, "Marca") or None
        modelo = self._get_attr(attrs, "Modelo") or None

        return AvisoAuto(
            fuente=self.fuente,
            id_externo=aviso_id,
            url=url,
            titulo=f"{marca or ''} {modelo or ''} {anio_s} usado precio {aviso_info['precio'].split(chr(10))[0]}".strip(),
            precio=precio,
            moneda="CLP",
            marca=marca,
            modelo=modelo,
            anio=anio,
            km=km,
            ubicacion=aviso_info["region"] or None,
            combustible=self._normalizar_combustible(self._get_attr(attrs, "Combustible")),
            descripcion=None,
            url_imagen=attrs.get("imagen_url") or None,
            disponible=True,
            fecha_publicacion=aviso_info["fecha"]
        )

    async def scrape(self) -> list[AvisoAuto]:
        avisos_validos = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="es-CL",
            )
            page = await ctx.new_page()
            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}", lambda route: route.abort())

            avisos_info = await self._recolectar_urls(page, max_paginas=3)
            logger.info(f"[{self.fuente}] {len(avisos_info)} URLs recolectadas.")

            for i, info in enumerate(avisos_info, 1):
                logger.debug(f"[{self.fuente}] Detalle {i}/{len(avisos_info)}: {info['url']}")
                aviso = await self._scrape_detalle(page, info)
                if aviso:
                    avisos_validos.append(aviso)
                await self.espera_aleatoria()

            await ctx.close()
            await browser.close()

        return avisos_validos
