"""Tests del scraper Económicos Cloud: parsers puros, validación, parseo de cards
y de la página de detalle, y un test de integración de scrape() con httpx mockeado."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from bs4 import BeautifulSoup

from carflip.scrapers.Economicos.economicosCloud import (
    ScraperEconomicosCloud,
    _marca_modelo_desde_titulo,
    _parsear_anio_titulo,
    _parsear_card,
    _parsear_km,
    _parsear_precio,
    _parsear_specs_detalle,
    _validar_aviso,
)
from carflip.scrapers.base import AvisoAuto


def _aviso_valido(**kw) -> AvisoAuto:
    base = dict(
        fuente="economicos",
        id_externo="abc123",
        url="https://www.economicos.cl/vehiculos/toyota-corolla-2025-araucania-cod1.html",
        titulo="Toyota Corolla 2.0 SEG 4X2 CVT AT 5P - 2025",
        precio=Decimal("21390000"),
        marca="Toyota",
        modelo="Corolla",
        anio=2025,
        km=28959,
        fecha_publicacion="2026-07-12",
        disponible=True,
    )
    base.update(kw)
    return AvisoAuto(**base)


class TestParsersEconomicos:
    """Funciones puras de parsing."""

    def test_parsear_precio_formateado(self):
        assert _parsear_precio("21.390.000") == Decimal("21390000")

    def test_parsear_precio_con_texto_alrededor(self):
        assert _parsear_precio("$ 8.500.000 aprox") == Decimal("8500000")

    def test_parsear_precio_sin_match(self):
        assert _parsear_precio("") is None
        assert _parsear_precio("Consultar") is None

    def test_parsear_km_formateado(self):
        assert _parsear_km("28.959 Kms") == 28959

    def test_parsear_km_sin_match(self):
        assert _parsear_km("") is None
        assert _parsear_km("sin datos") is None

    def test_parsear_anio_titulo_al_final(self):
        assert _parsear_anio_titulo("Toyota Corolla 2.0 SEG 4X2 CVT AT 5P - 2025") == 2025

    def test_parsear_anio_titulo_sin_match(self):
        assert _parsear_anio_titulo("Auto sin anio") is None

    def test_marca_modelo_desde_titulo(self):
        marca, modelo = _marca_modelo_desde_titulo("Nissan Navara 4x4 Diesel - 2024")
        assert marca == "Nissan"
        assert modelo == "Navara"

    def test_marca_modelo_titulo_vacio(self):
        assert _marca_modelo_desde_titulo("") == (None, None)


class TestValidacionEconomicos:
    """_validar_aviso: lista vacía = válido."""

    def test_aviso_valido(self):
        assert _validar_aviso(_aviso_valido()) == []

    def test_precio_bajo_minimo(self):
        errores = _validar_aviso(_aviso_valido(precio=Decimal("100000")))
        assert any("fuera de rango" in e for e in errores)

    def test_precio_sobre_maximo(self):
        errores = _validar_aviso(_aviso_valido(precio=Decimal("300000000")))
        assert any("fuera de rango" in e for e in errores)

    def test_anio_bajo_rango(self):
        errores = _validar_aviso(_aviso_valido(anio=1969))
        assert any("fuera de rango" in e for e in errores)

    def test_anio_sobre_rango(self):
        futuro = datetime.now().year + 5
        errores = _validar_aviso(_aviso_valido(anio=futuro))
        assert any("fuera de rango" in e for e in errores)

    def test_km_negativo(self):
        errores = _validar_aviso(_aviso_valido(km=-1))
        assert any("km" in e for e in errores)

    def test_fecha_futura(self):
        manana = (datetime.now().date() + timedelta(days=1)).isoformat()
        errores = _validar_aviso(_aviso_valido(fecha_publicacion=manana))
        assert any("futura" in e for e in errores)


_CARD_HTML = """
<div class="result row-fluid">
  <div class="col1 span2">
    <div id="tmb_mas_f"><div class="tmb"><div class="mas_img_result_bus">
      <div class="cont_img_tmb_mas_f">
        <a href="/vehiculos/toyota-corolla-2025-araucania-cod77373598.html">
          <div class="delayed-image-load" data-src="https://img/toyota.jpg?size=150"></div>
        </a>
      </div>
    </div></div></div>
  </div>
  <div class="col2 span6">
    <a href="/vehiculos/toyota-corolla-2025-araucania-cod77373598.html">
      <h3> Toyota Corolla 2.0 SEG 4X2 CVT AT 5P - 2025 </h3>
    </a>
  </div>
  <div class="col3 span3">
    <ul class="meta">
      <li class="ecn_precio"><i class="fa fa-usd"></i> 21.390.000</li>
      <li class="cort_txt"> Temuco | Araucanía</li>
      <li><i class="fa fa-clock-o"></i><time class="timeago" datetime="2026-07-12T16:08:00"></time></li>
    </ul>
  </div>
</div>
"""

_DETALLE_HTML = """
<html><body>
<div id="detalle">
  <div id="specs" class="span6">
    <h3 class="light">Ficha técnica</h3>
    <ul>
      <li><span>Marca:</span> Toyota</li>
      <li><span>Modelo:</span> Corolla</li>
      <li><span>Año:</span> 2025</li>
      <li><span>Combustible:</span> Bencina</li>
      <li><span>Transmision:</span> Automática</li>
      <li><span>Region:</span> Araucanía</li>
      <li><span>Fecha Publicación:</span> 2026-07-12 16:08:00</li>
    </ul>
  </div>
  <div id="description" class="span6">
    <h3 class="light">Descripción:</h3>
    <p>Toyota Corolla 2.0 SEG 4X2 CVT AT 5P 2025 $ 21.390.000 28.959 Kms</p>
  </div>
</div>
</body></html>
"""


class TestParseoCardEconomicos:
    """_parsear_card a partir de un div.result de BeautifulSoup."""

    def _card(self, html: str = _CARD_HTML):
        return BeautifulSoup(html, "lxml").find("div", class_="result")

    def test_parsea_card_completa(self):
        aviso = _parsear_card(self._card())
        assert aviso is not None
        assert aviso.titulo == "Toyota Corolla 2.0 SEG 4X2 CVT AT 5P - 2025"
        assert aviso.precio == Decimal("21390000")
        assert aviso.ubicacion == "Temuco | Araucanía"
        assert aviso.fecha_publicacion == "2026-07-12"
        assert aviso.url_imagen == "https://img/toyota.jpg"
        assert aviso.marca == "Toyota"
        assert aviso.modelo == "Corolla"
        assert aviso.anio == 2025
        assert aviso.disponible is True

    def test_href_que_no_es_aviso_retorna_none(self):
        html = '<div class="result"><a href="/otra-seccion">link</a></div>'
        card = BeautifulSoup(html, "lxml").find("div", class_="result")
        assert _parsear_card(card) is None


class TestParseoSpecsDetalle:
    def test_extrae_specs_y_descripcion(self):
        specs = _parsear_specs_detalle(_DETALLE_HTML)
        assert specs["Marca"] == "Toyota"
        assert specs["Modelo"] == "Corolla"
        assert specs["Año"] == "2025"
        assert specs["Combustible"] == "Bencina"
        assert "28.959 Kms" in specs["_descripcion"]


class TestScraperEconomicosCloudIntegracion:
    """scrape() end-to-end con httpx mockeado (sin red, sin disco, sin S3)."""

    async def test_scrape_filtra_invalidos_y_deduplica(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        card_barato = _CARD_HTML.replace("77373598", "999").replace("21.390.000", "100.000")
        html_listado_p1 = f'<html><body>{_CARD_HTML}{card_barato}</body></html>'
        html_listado_vacio = "<html><body></body></html>"

        async def _mock_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.status_code = 200
            resp.url = url
            if url == "https://www.economicos.cl/todo_chile/vehiculos":
                pagina = params.get("pagina", 1) if params else 1
                resp.text = html_listado_p1 if pagina == 1 else html_listado_vacio
            else:
                # página de detalle
                resp.text = _DETALLE_HTML
            return resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_mock_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "carflip.scrapers.Economicos.economicosCloud.httpx.AsyncClient",
            return_value=mock_client,
        ):
            scraper = ScraperEconomicosCloud(max_paginas=1, guardar_raw=False)
            avisos = await scraper.scrape()

        assert isinstance(avisos, list)
        assert all(isinstance(a, AvisoAuto) for a in avisos)
        # El aviso con precio $100.000 (bajo el mínimo) fue rechazado en validación
        assert len(avisos) == 1
        assert avisos[0].precio == Decimal("21390000")
        assert avisos[0].combustible == "Bencina"
