import asyncio
import random
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parents[3]))

import httpx
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent
from loguru import logger

from carflip.config import settings
from carflip.scrapers.base import AvisoAuto, ScraperBase

BASE_URL = "https://www.autocosmos.cl"
URL_USADOS = f"{BASE_URL}/auto/usado"

# Patrón de URL de aviso: /auto/usado/{marca}/{modelo}/{version}/{id}
_PATRON_AVISO = re.compile(r"^/auto/usado/[^/]+/[^/]+/[^/]+/(\d+)")


class AutocosmosClient:
    """Cliente HTTP para scraping de autos usados en Autocosmos Chile."""

    def __init__(self) -> None:
        self.ua = UserAgent()
        self.session: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AutocosmosClient":
        self.session = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.aclose()

    async def _hacer_request(self, url: str, params: dict | None = None) -> str:
        if not self.session:
            raise RuntimeError("Client debe usarse como context manager")
        headers = {"User-Agent": self.ua.random}
        try:
            response = await self.session.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            logger.error(f"[Autocosmos] Error en request a {url}: {e}")
            raise

    async def _descargar_imagen(self, url_imagen: str, ruta: Path) -> bool:
        """Descarga una imagen y la guarda en ruta. Retorna True si tuvo éxito."""
        if not self.session:
            return False
        try:
            headers = {"User-Agent": self.ua.random}
            response = await self.session.get(url_imagen, headers=headers)
            response.raise_for_status()
            ruta.write_bytes(response.content)
            return True
        except Exception as e:
            logger.warning(f"[Autocosmos] No se pudo descargar imagen {url_imagen}: {e}")
            return False

    @staticmethod
    def _parsear_precio(texto: str) -> Decimal | None:
        match = re.search(r"\$\s*([\d.,]+)", texto)
        if not match:
            return None
        try:
            limpio = match.group(1).replace(".", "").replace(",", "")
            return Decimal(limpio)
        except InvalidOperation:
            return None

    @staticmethod
    def _parsear_km(texto: str) -> int | None:
        match = re.search(r"([\d.,]+)\s*km", texto, re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _parsear_anio(texto: str) -> int | None:
        match = re.search(r"\b(19|20)\d{2}\b", texto)
        if not match:
            return None
        try:
            return int(match.group(0))
        except ValueError:
            return None

    @staticmethod
    def _parsear_ubicacion(texto: str) -> str | None:
        # Autocosmos muestra "Ciudad | Región" — buscamos la parte sin dígitos ni "$"
        partes = [p.strip() for p in texto.split("|")]
        for parte in partes:
            if parte and not re.search(r"[\d$]", parte):
                return parte
        return None

    def _parsear_aviso(self, tag: Tag) -> AvisoAuto | None:
        href = tag.get("href", "")
        match = _PATRON_AVISO.match(href)
        if not match:
            return None

        id_externo = match.group(1)
        url = urljoin(BASE_URL, href)

        # Marca y modelo desde segmentos de URL: /auto/usado/{marca}/{modelo}/{version}/{id}
        partes = href.rstrip("/").split("/")
        marca = partes[3].replace("-", " ").title() if len(partes) > 3 else None
        modelo = partes[4].replace("-", " ").title() if len(partes) > 4 else None

        img = tag.find("img")
        url_imagen: str | None = None
        titulo: str | None = None
        if isinstance(img, Tag):
            url_imagen = img.get("src") or img.get("data-src")
            titulo = img.get("alt")  # alt suele tener "Año Marca Modelo Versión"

        texto = tag.get_text(separator=" ", strip=True)
        if not titulo:
            titulo = texto[:200]

        return AvisoAuto(
            fuente="autocosmos",
            id_externo=id_externo,
            url=url,
            titulo=titulo or "",
            precio=self._parsear_precio(texto),
            moneda="CLP",
            marca=marca,
            modelo=modelo,
            anio=self._parsear_anio(texto),
            km=self._parsear_km(texto),
            ubicacion=self._parsear_ubicacion(texto),
            url_imagen=url_imagen,
            disponible=True,
        )

    async def fetch_usados(self, max_paginas: int | None = None) -> list[AvisoAuto]:
        """Obtiene avisos sin guardar. Útil cuando sólo se necesita la lista."""
        avisos: list[AvisoAuto] = []
        vistos: set[str] = set()
        logger.info("[Autocosmos] Iniciando fetch de autos usados")
        pagina = 1

        while max_paginas is None or pagina <= max_paginas:
            params = {"pidx": pagina}
            try:
                html = await self._hacer_request(URL_USADOS, params)
                cards = self._extraer_cards(html, vistos)
                if not cards:
                    logger.info(f"[Autocosmos] Página {pagina}: sin resultados, deteniendo")
                    break

                for card in cards:
                    try:
                        aviso = self._parsear_aviso(card)
                        if aviso:
                            avisos.append(aviso)
                    except Exception as e:
                        logger.warning(f"[Autocosmos] Error parseando aviso: {e}")

                logger.debug(f"[Autocosmos] Página {pagina}: {len(cards)} avisos")
                await asyncio.sleep(random.uniform(settings.min_delay_seconds, settings.max_delay_seconds))
                pagina += 1

            except Exception as e:
                logger.error(f"[Autocosmos] Error en página {pagina}: {e}")
                break

        logger.info(f"[Autocosmos] {len(avisos)} avisos obtenidos en total")
        return avisos

    def _extraer_cards(self, html: str, vistos: set[str] | None = None) -> list[Tag]:
        """Extrae los <a> de aviso de una página HTML, excluyendo hrefs ya vistos."""
        soup = BeautifulSoup(html, "lxml")
        local: set[str] = vistos if vistos is not None else set()
        cards: list[Tag] = []
        for a in soup.find_all("a", href=True):
            h = str(a.get("href", ""))
            if _PATRON_AVISO.match(h) and h not in local:
                local.add(h)
                cards.append(a)
        return cards

    async def fetch_all(
        self,
        max_paginas: int | None = None,
        guardar: bool = True,
        ruta_destino: Path | None = None,
    ) -> dict[str, list[AvisoAuto]]:
        """Obtiene todos los avisos.

        Si guardar=True, la imagen y el .md de cada aviso se escriben
        inmediatamente después de parsear esa tarjeta, antes de continuar
        con la siguiente — garantizando que imagen y datos siempre coincidan.
        """
        if not guardar:
            return {"usados": await self.fetch_usados(max_paginas)}

        destino = Path(ruta_destino or settings.output_dir)
        carpeta_imagenes = destino / "imagenes"
        carpeta_imagenes.mkdir(parents=True, exist_ok=True)

        avisos: list[AvisoAuto] = []
        vistos: set[str] = set()
        logger.info("[Autocosmos] Iniciando fetch con guardado inline")
        pagina = 1

        while max_paginas is None or pagina <= max_paginas:
            params = {"pidx": pagina}
            try:
                html = await self._hacer_request(URL_USADOS, params)
                cards = self._extraer_cards(html, vistos)
                if not cards:
                    logger.info(f"[Autocosmos] Página {pagina}: sin resultados, deteniendo")
                    break

                for card in cards:
                    try:
                        aviso = self._parsear_aviso(card)
                        if not aviso:
                            continue

                        # 1. Descargar imagen de ESTE aviso ahora mismo
                        ruta_img: Path | None = None
                        if aviso.url_imagen:
                            ext = Path(aviso.url_imagen.split("?")[0]).suffix or ".jpg"
                            ruta_img = carpeta_imagenes / f"{aviso.nombre_normalizado}{ext}"
                            if not ruta_img.exists():
                                await self._descargar_imagen(aviso.url_imagen, ruta_img)

                        # 2. Escribir el .md de ESTE aviso ahora mismo
                        ruta_md = destino / f"{aviso.nombre_normalizado}.md"
                        ruta_md.write_text(
                            _construir_markdown_aviso(aviso, ruta_img),
                            encoding="utf-8",
                        )

                        avisos.append(aviso)

                    except Exception as e:
                        logger.warning(f"[Autocosmos] Error procesando aviso: {e}")

                logger.debug(f"[Autocosmos] Página {pagina}: {len(cards)} avisos procesados")
                await asyncio.sleep(random.uniform(settings.min_delay_seconds, settings.max_delay_seconds))
                pagina += 1

            except Exception as e:
                logger.error(f"[Autocosmos] Error en página {pagina}: {e}")
                break

        logger.info(f"[Autocosmos] {len(avisos)} avisos guardados en {destino}")
        return {"usados": avisos}


def _valor(v: object) -> str:
    if v is None:
        return "—"
    if isinstance(v, Decimal):
        return f"${v:,.0f}"
    return str(v)


def _construir_markdown_aviso(aviso: AvisoAuto, ruta_img: Path | None) -> str:
    if ruta_img and ruta_img.exists():
        img_md = f"![{aviso.titulo}](imagenes/{ruta_img.name})"
    elif aviso.url_imagen:
        img_md = f"![{aviso.titulo}]({aviso.url_imagen})"
    else:
        img_md = ""

    lineas = [
        f"# {aviso.titulo}\n",
        img_md + "\n" if img_md else "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Fuente | {_valor(aviso.fuente)} |",
        f"| ID externo | {_valor(aviso.id_externo)} |",
        f"| URL | [{aviso.url}]({aviso.url}) |",
        f"| Precio | {_valor(aviso.precio)} {aviso.moneda} |",
        f"| Marca | {_valor(aviso.marca)} |",
        f"| Modelo | {_valor(aviso.modelo)} |",
        f"| Año | {_valor(aviso.anio)} |",
        f"| Kilometraje | {_valor(aviso.km)} |",
        f"| Combustible | {_valor(aviso.combustible)} |",
        f"| Ubicación | {_valor(aviso.ubicacion)} |",
        f"| Descripción | {_valor(aviso.descripcion)} |",
        f"| Disponible | {_valor(aviso.disponible)} |",
        f"| Fecha publicación | {_valor(aviso.fecha_publicacion)} |",
        f"| Imagen | {_valor(aviso.url_imagen)} |",
    ]

    return "\n".join(lineas)


class ScraperAutocosmos(ScraperBase):
    """Adaptador de AutocosmosClient a ScraperBase para integración con el runner."""

    fuente = "autocosmos"

    def __init__(self, max_paginas: int | None = None) -> None:
        self.max_paginas = max_paginas

    @property
    def model_class(self) -> type:  # type: ignore[override]
        from carflip.database.models import AutocosmosListing
        return AutocosmosListing

    async def scrape(self) -> list[AvisoAuto]:
        async with AutocosmosClient() as client:
            return await client.fetch_usados(max_paginas=self.max_paginas)


if __name__ == "__main__":
    async def _main() -> None:
        from carflip.database.models import AutocosmosListing
        from carflip.database.session import AsyncSessionLocal
        from carflip.database.uploader import upsert_avisos

        max_paginas = int(sys.argv[1]) if len(sys.argv) > 1 else None
        async with AutocosmosClient() as client:
            resultados = await client.fetch_all(max_paginas=max_paginas, guardar=True)
        usados = resultados["usados"]
        logger.info(f"Usados: {len(usados)}")
        for aviso in usados[:3]:
            logger.info(f"  {aviso.titulo} — ${aviso.precio} | {aviso.km} km | {aviso.anio}")

        if usados:
            async with AsyncSessionLocal() as session:
                n = await upsert_avisos(session, usados, AutocosmosListing)
            logger.info(f"[Autocosmos] {n} avisos subidos a la BD")

    asyncio.run(_main())
