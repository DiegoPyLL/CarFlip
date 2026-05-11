import asyncio
import random
import sys
from pathlib import Path
from decimal import Decimal

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parents[3]))

import httpx
from fake_useragent import UserAgent
from loguru import logger

from carflip.config import settings
from carflip.scrapers.base import AvisoAuto


class MercadoLibreClient:
    """Cliente HTTP para la API oficial de MercadoLibre Chile."""

    BASE_URL = "https://api.mercadolibre.com/sites/MLC/search"
    CATEGORIA_AUTOS = "MLC1744"
    CATEGORIA_MOTOS = "MLC1743"

    def __init__(self):
        self.ua = UserAgent()
        self.session: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self.session = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    async def _hacer_request(self, params: dict) -> dict:
        """Realiza un request HTTP con rate limiting."""
        if not self.session:
            raise RuntimeError("Client debe usarse como context manager")

        headers = {"User-Agent": self.ua.random}
        try:
            response = await self.session.get(
                self.BASE_URL,
                params=params,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Error en request a MercadoLibre: {e}")
            raise

    def _extraer_atributo(self, attributes: list[dict], attr_id: str) -> str | int | None:
        """Extrae un atributo específico de la lista de atributos del ítem."""
        for attr in attributes:
            if attr.get("id") == attr_id:
                value = attr.get("value_name")
                if attr_id == "VEHICLE_YEAR" and value:
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        return None
                elif attr_id == "KILOMETERS" and value:
                    try:
                        return int(value.replace(",", "").replace(".", ""))
                    except (ValueError, TypeError):
                        return None
                return value
        return None

    def _mapear_a_aviso(self, item: dict) -> AvisoAuto:
        """Mapea un ítem de la API de MercadoLibre a AvisoAuto."""
        attributes = item.get("attributes", [])

        anio = self._extraer_atributo(attributes, "VEHICLE_YEAR")
        km = self._extraer_atributo(attributes, "KILOMETERS")

        return AvisoAuto(
            fuente="mercadolibre",
            id_externo=item.get("id", ""),
            url=item.get("permalink", ""),
            titulo=item.get("title", ""),
            precio=Decimal(str(item.get("price", 0))) if item.get("price") else None,
            moneda=item.get("currency_id", "CLP"),
            marca=self._extraer_atributo(attributes, "BRAND"),
            modelo=self._extraer_atributo(attributes, "MODEL"),
            anio=anio,
            km=km,
            ubicacion=item.get("seller_address", {}).get("city", {}).get("name"),
            combustible=self._extraer_atributo(attributes, "FUEL_TYPE"),
            url_imagen=item.get("thumbnail"),
            disponible=item.get("status") == "active",
        )

    async def fetch_categoria(
        self, categoria: str, max_resultados: int = 200
    ) -> list[AvisoAuto]:
        """Obtiene todos los avisos de una categoría con paginación."""
        avisos: list[AvisoAuto] = []
        offset = 0
        limit = 50

        logger.info(f"[MercadoLibre] Iniciando fetch de categoría {categoria}")

        while len(avisos) < max_resultados:
            params: dict = {
                "category": categoria,
                "limit": limit,
                "offset": offset,
            }

            if settings.mercadolibre_app_id:
                params["app_id"] = settings.mercadolibre_app_id

            try:
                data = await self._hacer_request(params)
                items = data.get("results", [])

                if not items:
                    logger.info(f"[MercadoLibre] No hay más resultados en categoría {categoria}")
                    break

                for item in items:
                    if len(avisos) >= max_resultados:
                        break
                    try:
                        aviso = self._mapear_a_aviso(item)
                        avisos.append(aviso)
                    except Exception as e:
                        logger.warning(f"Error mapeando ítem {item.get('id')}: {e}")
                        continue

                paging = data.get("paging", {})
                total = paging.get("total", 0)

                if offset + limit >= total:
                    logger.info(f"[MercadoLibre] Fin de paginación en categoría {categoria}")
                    break

                offset += limit
                espera = random.uniform(settings.min_delay_seconds, settings.max_delay_seconds)
                logger.debug(f"[MercadoLibre] Esperando {espera:.2f}s antes del siguiente request")
                await asyncio.sleep(espera)

            except Exception as e:
                logger.error(f"Error fetching categoría {categoria}: {e}")
                break

        logger.info(f"[MercadoLibre] {len(avisos)} avisos obtenidos de {categoria}")
        return avisos

    async def fetch_todo(self, max_por_categoria: int = 200) -> dict[str, list[AvisoAuto]]:
        """Obtiene avisos de autos y motos."""
        autos = await self.fetch_categoria(self.CATEGORIA_AUTOS, max_por_categoria)
        motos = await self.fetch_categoria(self.CATEGORIA_MOTOS, max_por_categoria)

        return {
            "autos": autos,
            "motos": motos,
        }


if __name__ == "__main__":
    async def _main() -> None:
        max_avisos = int(sys.argv[1]) if len(sys.argv) > 1 else 10
        async with MercadoLibreClient() as client:
            resultados = await client.fetch_todo(max_por_categoria=max_avisos)
        autos = resultados["autos"]
        motos = resultados["motos"]
        logger.info(f"Autos: {len(autos)} | Motos: {len(motos)}")
        for aviso in autos[:3]:
            logger.info(f"  {aviso.titulo} — ${aviso.precio} {aviso.moneda}")

    asyncio.run(_main())
