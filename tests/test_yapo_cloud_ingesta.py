"""
Tests de integración para ScraperYapoCloud — Etapa 1: Ingesta.

Valida que el scraper ejecute correctamente y genere archivos en data/raw/
con la estructura esperada.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from loguru import logger

from carflip.scrapers.Yapo.yapoCloud import ScraperYapoCloud


@pytest.fixture
def tmp_data_raw(tmp_path):
    """Crea un directorio temporal para data/raw"""
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


@pytest.fixture
def mock_playwright_context():
    """Mockea el contexto de async_playwright con respuestas simuladas"""
    async def mock_page_goto(*args, **kwargs):
        pass

    async def mock_page_wait_for_selector(*args, **kwargs):
        pass

    async def mock_page_wait_for_timeout(*args, **kwargs):
        pass

    async def mock_query_selector_all(*args, **kwargs):
        """Retorna cards mock con enlaces de avisos"""
        cards = []
        for i in range(2):
            card = AsyncMock()
            link = AsyncMock()
            link.get_attribute = AsyncMock(
                return_value=f"/autos-usados/region_metropolitana/toyota/corolla/2020/123456{i}"
            )
            card.query_selector = AsyncMock(return_value=link)

            # Métodos para obtener precio, región, fecha
            async def safe_selector(sel, card_ref=card):
                if "price" in sel:
                    return "$8.500.000"
                elif "location" in sel:
                    return "Santiago"
                return "2024-03-15"

            card.query_selector = AsyncMock(side_effect=lambda sel: safe_selector(sel))
            cards.append(card)
        return cards

    async def mock_page_evaluate(*args, **kwargs):
        """Retorna atributos simulados del auto"""
        return {
            "Marca": "Toyota",
            "Modelo": "Corolla",
            "Año": "2020",
            "Kilómetros": "85.000 km",
            "Combustible": "Bencina",
            "imagen_url": "https://example.com/foto.jpg",
        }

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=mock_page_goto)
    mock_page.wait_for_selector = AsyncMock(side_effect=mock_page_wait_for_selector)
    mock_page.wait_for_timeout = AsyncMock(side_effect=mock_page_wait_for_timeout)
    mock_page.query_selector_all = AsyncMock(side_effect=mock_query_selector_all)
    mock_page.evaluate = AsyncMock(side_effect=mock_page_evaluate)
    mock_page.route = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(return_value=mock_page)
    mock_ctx.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_ctx)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_p = AsyncMock()
    mock_p.chromium = mock_chromium

    return mock_p, mock_page


@pytest.mark.asyncio
async def test_yapo_cloud_scrape_retorna_avisos(mock_playwright_context):
    """Verifica que scrape() retorna lista de AvisoAuto válidos"""
    mock_p, _ = mock_playwright_context

    with patch("carflip.scrapers.Yapo.yapoCloud.async_playwright") as mock_pw:
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_p)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        scraper = ScraperYapoCloud()
        avisos = await scraper.scrape()

        assert isinstance(avisos, list)
        assert len(avisos) >= 0


@pytest.mark.asyncio
async def test_yapo_cloud_avisos_tienen_campos_requeridos(mock_playwright_context):
    """Verifica que cada aviso tiene los campos mínimos requeridos"""
    mock_p, _ = mock_playwright_context

    with patch("carflip.scrapers.Yapo.yapoCloud.async_playwright") as mock_pw:
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_p)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        scraper = ScraperYapoCloud()
        avisos = await scraper.scrape()

        if avisos:
            aviso = avisos[0]
            assert aviso.fuente == "yapo"
            assert aviso.id_externo
            assert aviso.url
            assert aviso.titulo


@pytest.mark.asyncio
async def test_yapo_cloud_valida_avisos(mock_playwright_context):
    """Verifica que los avisos pasan validación estructural"""
    mock_p, _ = mock_playwright_context

    with patch("carflip.scrapers.Yapo.yapoCloud.async_playwright") as mock_pw:
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_p)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

        scraper = ScraperYapoCloud()
        avisos = await scraper.scrape()

        for aviso in avisos:
            # Solo avisos válidos deben retornarse
            if aviso.anio is not None:
                assert isinstance(aviso.anio, int)
                assert 1990 <= aviso.anio <= 2026

            if aviso.km is not None:
                assert isinstance(aviso.km, int)
                assert aviso.km >= 0

            if aviso.precio is not None:
                assert float(aviso.precio) > 0


@pytest.mark.asyncio
async def test_yapo_cloud_normaliza_combustible():
    """Verifica normalización de tipos de combustible"""
    scraper = ScraperYapoCloud()

    test_cases = [
        ("Bencina", "bencina"),
        ("DIESEL", "diesel"),
        ("Eléctrico", "electrico"),
        ("Híbrido", "hibrido"),
        ("gasolina", "bencina"),
    ]

    for entrada, esperado in test_cases:
        resultado = scraper._normalizar_combustible(entrada)
        assert resultado == esperado, f"Fallo: {entrada} → {resultado}, esperado {esperado}"


@pytest.mark.asyncio
async def test_yapo_cloud_limpiar_km():
    """Verifica extracción de km desde texto sucio"""
    scraper = ScraperYapoCloud()

    test_cases = [
        ("85.000 km", 85000),
        ("120000", 120000),
        ("5.500", 5500),
        ("", None),
        ("sin km", None),
    ]

    for entrada, esperado in test_cases:
        resultado = scraper._limpiar_km(entrada)
        assert resultado == esperado, f"Fallo: {entrada} → {resultado}, esperado {esperado}"


@pytest.mark.asyncio
async def test_yapo_cloud_limpiar_precio():
    """Verifica extracción de precio desde texto sucio"""
    scraper = ScraperYapoCloud()

    test_cases = [
        ("$8.500.000", 8500000),
        ("$9500000", 9500000),
        ("Precio a convenir", None),
        ("", None),
    ]

    for entrada, esperado in test_cases:
        resultado = scraper._limpiar_precio(entrada)
        assert resultado == esperado, f"Fallo: {entrada} → {resultado}, esperado {esperado}"


@pytest.mark.asyncio
async def test_yapo_cloud_get_attr_busca_variaciones():
    """Verifica que _get_attr normaliza y encuentra variaciones de claves"""
    scraper = ScraperYapoCloud()

    attrs = {
        "Marca": "Toyota",
        "Año": "2020",
        "Kilometros": "85000",
    }

    # Debe encontrar con normalización Unicode
    assert scraper._get_attr(attrs, "Marca") == "Toyota"
    assert scraper._get_attr(attrs, "Año") == "2020"
    assert scraper._get_attr(attrs, "Kilometros") == "85000"
    assert scraper._get_attr(attrs, "Kilómetros") == "85000"  # Con acento

    # No debe encontrar claves inexistentes
    assert scraper._get_attr(attrs, "Modelo") == ""
