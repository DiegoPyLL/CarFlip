"""Tests del scraper Autocosmos Cloud: parsers puros, validación, parseo de cards
y un test de integración de scrape() con httpx mockeado."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bs4 import BeautifulSoup

from carflip.scrapers.AutoCosmos.autocosmosCloud import (
    ScraperAutocosmosCloud,
    _aviso_a_dict,
    _parsear_anio,
    _parsear_aviso,
    _parsear_km,
    _parsear_precio,
    _parsear_ubicacion,
    _validar_aviso,
)
from carflip.scrapers.base import AvisoAuto


def _aviso_valido(**kw) -> AvisoAuto:
    base = dict(
        fuente="autocosmos",
        id_externo="abc123",
        url="https://www.autocosmos.cl/auto/usado/toyota/corolla/1",
        titulo="Toyota Corolla 2020",
        precio=Decimal("8000000"),
        marca="Toyota",
        modelo="Corolla",
        anio=2020,
        km=50000,
        fecha_publicacion="2020-01-15",
        disponible=True,
    )
    base.update(kw)
    return AvisoAuto(**base)


class TestParsersAutocosmos:
    """Funciones puras de parsing."""

    def test_parsear_precio_clp_formateado(self):
        assert _parsear_precio("$ 8.500.000") == Decimal("8500000")

    def test_parsear_precio_sin_separadores(self):
        assert _parsear_precio("$12300000") == Decimal("12300000")

    def test_parsear_precio_sin_match(self):
        assert _parsear_precio("") is None
        assert _parsear_precio("Precio a convenir") is None

    def test_parsear_km_formateado(self):
        assert _parsear_km("85.000 km") == 85000

    def test_parsear_km_sin_separadores(self):
        assert _parsear_km("120000km") == 120000

    def test_parsear_km_sin_match(self):
        assert _parsear_km("") is None
        assert _parsear_km("sin kilometraje") is None

    def test_parsear_anio_directo(self):
        assert _parsear_anio("2020") == 2020

    def test_parsear_anio_embebido(self):
        assert _parsear_anio("Toyota Corolla 2019 usado") == 2019

    def test_parsear_anio_sin_match(self):
        assert _parsear_anio("") is None
        assert _parsear_anio("Auto sin anio") is None

    def test_parsear_ubicacion_con_pipe(self):
        assert _parsear_ubicacion("Santiago | $ 8.500.000") == "Santiago"

    def test_parsear_ubicacion_descarta_partes_con_digitos(self):
        assert _parsear_ubicacion("$8500000 | 2020") is None


class TestValidacionAutocosmos:
    """_validar_aviso: lista vacía = válido."""

    def test_aviso_valido(self):
        assert _validar_aviso(_aviso_valido()) == []

    def test_precio_bajo_minimo(self):
        errores = _validar_aviso(_aviso_valido(precio=Decimal("100000")))
        assert any("fuera de rango" in e for e in errores)

    def test_precio_sobre_maximo(self):
        errores = _validar_aviso(_aviso_valido(precio=Decimal("300000000")))
        assert any("fuera de rango" in e for e in errores)

    def test_precio_no_positivo(self):
        errores = _validar_aviso(_aviso_valido(precio=Decimal("-100")))
        assert any("> 0" in e for e in errores)

    def test_anio_bajo_rango(self):
        errores = _validar_aviso(_aviso_valido(anio=1969))
        assert any("fuera de rango" in e for e in errores)

    def test_anio_sobre_rango(self):
        futuro = datetime.now().year + 5
        errores = _validar_aviso(_aviso_valido(anio=futuro))
        assert any("fuera de rango" in e for e in errores)

    def test_anio_formato_invalido(self):
        errores = _validar_aviso(_aviso_valido(anio=999))
        assert any("formato" in e for e in errores)

    def test_km_negativo(self):
        errores = _validar_aviso(_aviso_valido(km=-1))
        assert any("km" in e for e in errores)

    def test_fecha_formato_invalido(self):
        errores = _validar_aviso(_aviso_valido(fecha_publicacion="15-01-2020"))
        assert any("YYYY-MM-DD" in e for e in errores)

    def test_fecha_futura(self):
        manana = (datetime.now().date() + timedelta(days=1)).isoformat()
        errores = _validar_aviso(_aviso_valido(fecha_publicacion=manana))
        assert any("futura" in e for e in errores)


class TestParseoAvisoAutocosmos:
    """_parsear_aviso a partir de un tag <a> de BeautifulSoup."""

    def _tag(self, html: str):
        return BeautifulSoup(html, "lxml").find("a")

    def test_parsea_card_completa(self):
        tag = self._tag(
            '<a href="/auto/usado/ford/fiesta/hatchback/12345">'
            '<img src="https://img/x.webp" alt="Ford Fiesta 2020"/>'
            " Santiago | $ 5.000.000 | 100.000 km | 2020</a>"
        )
        aviso = _parsear_aviso(tag)
        assert aviso is not None
        assert aviso.marca == "Ford"
        assert aviso.modelo == "Fiesta"
        assert aviso.precio == Decimal("5000000")
        assert aviso.km == 100000
        assert aviso.anio == 2020
        assert aviso.titulo == "Ford Fiesta 2020"
        assert aviso.url_imagen == "https://img/x.webp"
        assert aviso.disponible is True

    def test_href_que_no_es_aviso_retorna_none(self):
        tag = self._tag('<a href="/seccion/otra-cosa">link</a>')
        assert _parsear_aviso(tag) is None


class TestAvisoDictAutocosmos:
    """_aviso_a_dict serializa a dict apto para JSON."""

    def test_precio_decimal_a_int(self):
        d = _aviso_a_dict(_aviso_valido(precio=Decimal("8500000")))
        assert d["precio"] == 8500000
        assert isinstance(d["precio"], int)

    def test_precio_none(self):
        d = _aviso_a_dict(_aviso_valido(precio=None))
        assert d["precio"] is None

    def test_incluye_foto_local(self):
        d = _aviso_a_dict(_aviso_valido(), foto_local="abc123.jpg")
        assert d["foto_local"] == "abc123.jpg"


class TestScraperAutocosmosCloudIntegracion:
    """scrape() end-to-end con httpx mockeado (sin red, sin disco, sin S3)."""

    async def test_scrape_filtra_invalidos_y_deduplica(
        self, html_listado_autocosmos, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)

        mock_response = MagicMock()
        mock_response.text = html_listado_autocosmos
        mock_response.status_code = 200
        mock_response.url = "https://www.autocosmos.cl/auto/usado?pidx=1"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "carflip.scrapers.AutoCosmos.autocosmosCloud.httpx.AsyncClient",
            return_value=mock_client,
        ):
            scraper = ScraperAutocosmosCloud(max_paginas=1, guardar_raw=False)
            avisos = await scraper.scrape()

        assert isinstance(avisos, list)
        assert all(isinstance(a, AvisoAuto) for a in avisos)
        # El aviso con precio $100.000 (bajo el mínimo) fue rechazado en validación
        assert len(avisos) == 2
        # Sin duplicados por id_externo
        ids = [a.id_externo for a in avisos]
        assert len(ids) == len(set(ids))
        # Todos dentro del rango de precio válido
        assert all(a.precio is not None and a.precio >= Decimal("500000") for a in avisos)
