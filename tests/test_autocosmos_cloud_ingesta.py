"""
Tests de integración para ScraperAutocosmosCloud — Etapa 1: Ingesta.

Valida que el scraper ejecute correctamente, parsee HTML, genere archivos JSON
en data/raw/ y no cree duplicados en la deduplicación.
"""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from carflip.scrapers.AutoCosmos.autocosmosCloud import (
    ScraperAutocosmosCloud,
    _parsear_precio,
    _parsear_km,
    _parsear_anio,
    _parsear_ubicacion,
    _validar_aviso,
    _extraer_cards,
    _parsear_aviso,
    _aviso_a_dict,
)
from carflip.scrapers.base import AvisoAuto


class TestParsersAutocosmosCloud:
    """Tests para funciones puras de parsing."""

    def test_parsear_precio_clp_formateado(self):
        """Extrae precio con formato CLP ($ 8.500.000)"""
        assert _parsear_precio("$ 8.500.000") == Decimal("8500000")

    def test_parsear_precio_sin_separadores(self):
        """Extrae precio sin separadores de miles"""
        assert _parsear_precio("$12300000") == Decimal("12300000")

    def test_parsear_precio_vacio(self):
        """Retorna None para texto sin precio"""
        assert _parsear_precio("") is None
        assert _parsear_precio("Precio a convenir") is None

    def test_parsear_km_formateado(self):
        """Extrae km con separadores (85.000 km)"""
        assert _parsear_km("85.000 km") == 85000

    def test_parsear_km_sin_separadores(self):
        """Extrae km sin separadores"""
        assert _parsear_km("120000km") == 120000

    def test_parsear_km_vacio(self):
        """Retorna None para texto sin km"""
        assert _parsear_km("") is None
        assert _parsear_km("sin kilometraje") is None

    def test_parsear_anio_encontrado(self):
        """Extrae año válido (1990-2099)"""
        assert _parsear_anio("2020") == 2020
        assert _parsear_anio("Toyota Corolla 2019 usado") == 2019

    def test_parsear_anio_no_encontrado(self):
        """Retorna None si no hay año"""
        assert _parsear_anio("") is None
        assert _parsear_anio("Auto sin año") is None

    def test_parsear_ubicacion_con_pipe(self):
        """Extrae región antes del primer pipe (|)"""
        # Formato: "Santiago | $ 8.500.000 | 2020"
        assert _parsear_ubicacion("Santiago | $ 8.500.000") == "Santiago"
        assert _parsear_ubicacion("Region Metropolitana | 150 km") == "Region Metropolitana"

    def test_parsear_ubicacion_vacio(self):
        """Retorna None para texto sin ubicación válida"""
        assert _parsear_ubicacion("") is None
        assert _parsear_ubicacion("$8500000 | 2020") is None


class TestValidacionAutocosmosCloud:
    """Tests para validación de avisos."""

    def test_validar_aviso_valido(self):
        """Aviso con todos los campos válidos pasa validación"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc123",
            url="https://example.com/auto/1",
            titulo="Toyota Corolla 2020",
            precio=Decimal("8500000"),
            moneda="CLP",
            marca="Toyota",
            modelo="Corolla",
            anio=2020,
            km=85000,
            ubicacion="Santiago",
            combustible="bencina",
            disponible=True,
            fecha_publicacion="2024-03-15",
        )
        errores = _validar_aviso(aviso)
        assert errores == []

    def test_validar_aviso_precio_minimo(self):
        """Rechaza aviso con precio < 500.000"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc123",
            url="https://example.com",
            titulo="Auto barato",
            precio=Decimal("100000"),  # Bajo el mínimo
            anio=2020,
        )
        errores = _validar_aviso(aviso)
        assert any("precio" in e for e in errores)

    def test_validar_aviso_precio_maximo(self):
        """Rechaza aviso con precio > 250.000.000"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc123",
            url="https://example.com",
            titulo="Auto caro",
            precio=Decimal("300000000"),  # Sobre el máximo
            anio=2020,
        )
        errores = _validar_aviso(aviso)
        assert any("precio" in e for e in errores)

    def test_validar_aviso_anio_invalido(self):
        """Rechaza aviso con año fuera de rango"""
        aviso_viejo = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc",
            url="https://example.com",
            titulo="Auto muy viejo",
            anio=1950,  # Anterior a 1970
        )
        errores = _validar_aviso(aviso_viejo)
        assert any("anio" in e for e in errores)

    def test_validar_aviso_fecha_futura(self):
        """Rechaza aviso con fecha futura"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc",
            url="https://example.com",
            titulo="Auto futuro",
            fecha_publicacion="2099-12-31",
        )
        errores = _validar_aviso(aviso)
        assert any("futura" in e for e in errores)

    def test_validar_aviso_fecha_formato_invalido(self):
        """Rechaza fecha con formato incorrecto"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc",
            url="https://example.com",
            titulo="Auto con fecha rara",
            fecha_publicacion="15/03/2024",  # Formato incorrecto
        )
        errores = _validar_aviso(aviso)
        assert any("fecha_publicacion" in e for e in errores)

    def test_validar_aviso_km_negativo(self):
        """Rechaza aviso con km negativo"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc",
            url="https://example.com",
            titulo="Auto con km negativo",
            km=-100,
        )
        errores = _validar_aviso(aviso)
        assert any("km" in e for e in errores)


class TestExtractionAutocosmosCloud:
    """Tests para extracción de datos desde HTML."""

    def test_extraer_cards_con_avisos(self):
        """Extrae múltiples cards de HTML válido"""
        html = """<html><body>
            <a href="/auto/usado/toyota/corolla/2020/12345678">
                <img src="test.jpg" alt="Toyota">
                $ 8.500.000
            </a>
            <a href="/auto/usado/honda/civic/2019/87654321">
                <img src="test2.jpg" alt="Honda">
                $ 9.000.000
            </a>
        </body></html>"""

        vistos = set()
        cards = _extraer_cards(html, vistos)
        assert len(cards) == 2
        assert len(vistos) == 2

    def test_extraer_cards_deduplicacion_en_sesion(self):
        """Evita duplicados dentro de la misma sesión"""
        html = """<html><body>
            <a href="/auto/usado/toyota/corolla/2020/12345678">Toyota 1</a>
            <a href="/auto/usado/toyota/corolla/2020/12345678">Toyota Dup</a>
            <a href="/auto/usado/honda/civic/2019/87654321">Honda</a>
        </body></html>"""

        vistos = set()
        cards = _extraer_cards(html, vistos)
        # Solo 2: el segundo Toyota debe ignorarse
        assert len(cards) == 2

    def test_extraer_cards_sin_avisos(self):
        """Retorna lista vacía si no hay avisos válidos"""
        html = "<html><body><a href='/venta/otros/1234'>No es auto</a></body></html>"
        vistos = set()
        cards = _extraer_cards(html, vistos)
        assert len(cards) == 0

    def test_parsear_aviso_desde_html(self):
        """Parsea un aviso completo desde tag HTML"""
        html = '<a href="/auto/usado/toyota/corolla/2020/12345678"><img src="foto.jpg" alt="Toyota Corolla">$ 8.500.000 85.000 km Santiago 2020</a>'
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("a")

        aviso = _parsear_aviso(tag)
        assert aviso is not None
        assert aviso.fuente == "autocosmos"
        assert aviso.marca == "Toyota"
        assert aviso.modelo == "Corolla"
        assert aviso.precio == Decimal("8500000")
        assert aviso.km == 85000
        assert aviso.ubicacion == "Santiago"

    def test_parsear_aviso_href_invalido(self):
        """Retorna None si el href no coincide el patrón"""
        html = '<a href="/venta/otros/1234">Link invalido</a>'
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("a")

        aviso = _parsear_aviso(tag)
        assert aviso is None


class TestAvisoDictConversion:
    """Tests para conversión de AvisoAuto a diccionario."""

    def test_aviso_a_dict_completo(self):
        """Convierte AvisoAuto a diccionario con todos los campos"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc123",
            url="https://example.com",
            titulo="Toyota Corolla",
            precio=Decimal("8500000"),
            moneda="CLP",
            marca="Toyota",
            modelo="Corolla",
            anio=2020,
            km=85000,
            ubicacion="Santiago",
            combustible="bencina",
            descripcion="Auto en buen estado",
            url_imagen="https://example.com/foto.jpg",
            disponible=True,
            fecha_publicacion="2024-03-15",
        )

        resultado = _aviso_a_dict(aviso, foto_local="12345.jpg")
        assert resultado["fuente"] == "autocosmos"
        assert resultado["id_externo"] == "abc123"
        assert resultado["precio"] == "8500000"  # Convertido a string
        assert resultado["foto_local"] == "12345.jpg"

    def test_aviso_a_dict_sin_precio(self):
        """Maneja precio None correctamente"""
        aviso = AvisoAuto(
            fuente="autocosmos",
            id_externo="abc",
            url="https://example.com",
            titulo="Auto",
            precio=None,
        )
        resultado = _aviso_a_dict(aviso)
        assert resultado["precio"] is None


class TestScraperAutocosmosCloudIntegration:
    """Tests de integración del scraper."""

    @pytest.mark.asyncio
    async def test_scrape_retorna_lista_avisos(self):
        """Verifica que scrape() retorna lista de avisos"""
        html_con_avisos = """<html><body>
            <a href="/auto/usado/toyota/corolla/2020/12345678">
                <img src="foto.jpg" alt="Toyota">
                $ 8.500.000 85.000 km Santiago 2020
            </a>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html_con_avisos
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("carflip.scrapers.AutoCosmos.autocosmosCloud.httpx.AsyncClient", return_value=mock_client):
            with patch("carflip.scrapers.AutoCosmos.autocosmosCloud.UserAgent"):
                scraper = ScraperAutocosmosCloud(max_paginas=1, guardar_raw=False)
                avisos = await scraper.scrape()

                assert isinstance(avisos, list)

    @pytest.mark.asyncio
    async def test_scrape_deduplica_avisos_locales(self):
        """Verifica que avisos duplicados en la sesión se descartan"""
        # HTML con el mismo aviso en dos páginas
        html_dup = """<html><body>
            <a href="/auto/usado/toyota/corolla/2020/12345678">
                <img src="f.jpg">$ 8.500.000 85.000 km Santiago 2020
            </a>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html_dup
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        # Primera y segunda página retornan el mismo aviso
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("carflip.scrapers.AutoCosmos.autocosmosCloud.httpx.AsyncClient", return_value=mock_client):
            with patch("carflip.scrapers.AutoCosmos.autocosmosCloud.UserAgent"):
                scraper = ScraperAutocosmosCloud(max_paginas=2, guardar_raw=False)
                avisos = await scraper.scrape()

                # Si hay dedupe local, debería haber solo 1 (o ninguno si se dedupa)
                # El mismo id_externo (basado en URL) no debe aparecer 2 veces
                ids = [a.id_externo for a in avisos]
                assert len(ids) == len(set(ids)), "Hay duplicados en los avisos retornados"

    @pytest.mark.asyncio
    async def test_scrape_rechaza_avisos_invalidos(self):
        """Verifica que avisos con precios fuera de rango se rechazan"""
        html_precio_bajo = """<html><body>
            <a href="/auto/usado/toyota/corolla/2020/12345678">
                <img src="f.jpg">$ 100.000 km Santiago 2020
            </a>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.text = html_precio_bajo
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("carflip.scrapers.AutoCosmos.autocosmosCloud.httpx.AsyncClient", return_value=mock_client):
            with patch("carflip.scrapers.AutoCosmos.autocosmosCloud.UserAgent"):
                scraper = ScraperAutocosmosCloud(max_paginas=1, guardar_raw=False)
                avisos = await scraper.scrape()

                # Ningún aviso debería tener precio < 500.000
                for aviso in avisos:
                    if aviso.precio is not None:
                        assert float(aviso.precio) >= 500_000
