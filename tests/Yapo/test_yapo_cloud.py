"""Tests del scraper Yapo Cloud: helpers de ID, parsers de instancia, validación
y un test de integración de scrape() con Playwright mockeado."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from carflip.scrapers.Yapo.yapoCloud import (
    ScraperYapoCloud,
    _aviso_a_dict,
    _id_nativo_yapo,
    _validar_aviso,
)
from carflip.scrapers.base import AvisoAuto


@pytest.fixture
def scraper() -> ScraperYapoCloud:
    return ScraperYapoCloud(max_paginas=1, guardar_raw=False)


def _aviso_valido(**kw) -> AvisoAuto:
    base = dict(
        fuente="yapo",
        id_externo="123456",
        url="https://www.yapo.cl/autos-usados/toyota/corolla/123456",
        titulo="Toyota Corolla 2020 usado",
        precio=Decimal("8500000"),
        marca="Toyota",
        modelo="Corolla",
        anio=2020,
        km=85000,
        fecha_publicacion="2024-03-15",
        disponible=True,
    )
    base.update(kw)
    return AvisoAuto(**base)


class TestIdNativoYapo:
    """_id_nativo_yapo: último segmento numérico, o hash de 16 hex como fallback."""

    def test_segmento_numerico(self):
        assert _id_nativo_yapo("https://www.yapo.cl/autos-usados/toyota/corolla/123456") == "123456"

    def test_fallback_hash(self):
        out = _id_nativo_yapo("https://www.yapo.cl/autos-usados/toyota-corolla")
        assert len(out) == 16
        assert all(c in "0123456789abcdef" for c in out)


class TestParsersYapo:
    """Métodos de parsing de instancia."""

    def test_get_attr_normaliza_acentos_y_mayusculas(self, scraper):
        assert scraper._get_attr({"Año": "2020"}, "Ano", "Año") == "2020"

    def test_get_attr_clave_ausente(self, scraper):
        assert scraper._get_attr({"Marca": "Toyota"}, "Modelo") == ""

    def test_limpiar_km_con_puntos(self, scraper):
        assert scraper._limpiar_km("85.000") == 85000

    def test_limpiar_km_con_comillas(self, scraper):
        assert scraper._limpiar_km("120'000") == 120000

    def test_limpiar_km_con_unidad_es_none(self, scraper):
        # El sufijo de unidad ("km") deja caracteres no numéricos → None
        assert scraper._limpiar_km("85.000 km") is None

    def test_limpiar_km_sin_digitos(self, scraper):
        assert scraper._limpiar_km("sin datos") is None

    def test_limpiar_precio_primera_linea(self, scraper):
        assert scraper._limpiar_precio("$ 5.000.000\notra linea") == 5000000

    def test_limpiar_precio_sin_digitos(self, scraper):
        assert scraper._limpiar_precio("abc") is None

    def test_normalizar_combustible(self, scraper):
        assert scraper._normalizar_combustible("Eléctrico") == "electrico"
        assert scraper._normalizar_combustible("Híbrido") == "hibrido"
        assert scraper._normalizar_combustible("Diésel") == "diesel"
        assert scraper._normalizar_combustible("Gasolina") == "bencina"

    def test_normalizar_combustible_vacio(self, scraper):
        assert scraper._normalizar_combustible("") is None


class TestValidacionYapo:
    """_validar_aviso (misma lógica que Autocosmos)."""

    def test_aviso_valido(self):
        assert _validar_aviso(_aviso_valido()) == []

    def test_precio_fuera_de_rango(self):
        assert any("fuera de rango" in e for e in _validar_aviso(_aviso_valido(precio=Decimal("100000"))))

    def test_anio_fuera_de_rango(self):
        assert any("fuera de rango" in e for e in _validar_aviso(_aviso_valido(anio=1969)))

    def test_anio_formato_invalido(self):
        assert any("formato" in e for e in _validar_aviso(_aviso_valido(anio=999)))

    def test_km_negativo(self):
        assert any("km" in e for e in _validar_aviso(_aviso_valido(km=-1)))

    def test_fecha_futura(self):
        manana = (datetime.now().date() + timedelta(days=1)).isoformat()
        assert any("futura" in e for e in _validar_aviso(_aviso_valido(fecha_publicacion=manana)))


class TestAvisoDictYapo:
    """_aviso_a_dict serializa a dict apto para JSON."""

    def test_precio_decimal_a_int(self):
        assert _aviso_a_dict(_aviso_valido(precio=Decimal("8500000")))["precio"] == 8500000

    def test_precio_none(self):
        assert _aviso_a_dict(_aviso_valido(precio=None))["precio"] is None


class TestScraperYapoCloudIntegracion:
    """scrape() end-to-end con Playwright y httpx mockeados (frágil; ver CLAUDE.md)."""

    async def test_scrape_retorna_avisos_validos(self, mock_playwright, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        mock_async_playwright, _page = mock_playwright

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "carflip.scrapers.Yapo.yapoCloud.async_playwright", mock_async_playwright
        ), patch(
            "carflip.scrapers.Yapo.yapoCloud.httpx.AsyncClient", return_value=mock_client
        ):
            scraper = ScraperYapoCloud(max_paginas=1, guardar_raw=False)
            avisos = await scraper.scrape()

        assert isinstance(avisos, list)
        assert len(avisos) == 2
        ids = [a.id_externo for a in avisos]
        assert len(ids) == len(set(ids))
        for a in avisos:
            assert a.fuente == "yapo"
            assert a.id_externo
            assert a.url
            assert a.marca == "Toyota"
            assert a.anio == 2020
