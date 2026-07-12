"""Tests del scraper Checkeados Cloud: parsers puros sobre el sitemap y el JSON
__NEXT_DATA__ del detalle, validación, y un test de integración de scrape()
con httpx mockeado."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from carflip.scrapers.Checkeados.checkeadosCloud import (
    ScraperCheckeadosCloud,
    _extraer_vehicle,
    _parsear_vehicle,
    _urls_desde_sitemap,
    _validar_aviso,
)
from carflip.scrapers.base import AvisoAuto

_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.checkeados.cl/comprar</loc></url>
  <url><loc>https://www.checkeados.cl/comprar/hyundai~accent~2023~2d26</loc></url>
  <url><loc>https://www.checkeados.cl/comprar/suzuki~swift~2025~2846</loc></url>
</urlset>
"""


def _vehicle_valido(**kw) -> dict:
    base = dict(
        id="2d2683b5-281a-44ed-b78d-c0806c9c6976",
        brand="HYUNDAI",
        model="ACCENT",
        version="1.4 HCI PLUS MT",
        year=2023,
        kms=74701,
        transmission="Manual",
        fuel="Bencina",
        price=10790000,
        publicationDate="2026-02-25T15:19:12.263Z",
        status="Publicado",
        mainImageUrl="https://d2k67dszumfzw5.cloudfront.net/production/x/1.png",
        description="Comandos al volante, luces automáticas.",
        branch={"id": "b1", "name": "Movicenter"},
        images=[{"id": "i1", "url": "https://d2k67dszumfzw5.cloudfront.net/production/x/1.png"}],
    )
    base.update(kw)
    return base


def _html_next_data_detalle(vehicle: dict | None) -> str:
    data = {"props": {"pageProps": {"vehicle": vehicle}}}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


def _aviso_valido(**kw) -> AvisoAuto:
    base = dict(
        fuente="checkeados",
        id_externo="abc123",
        url="https://www.checkeados.cl/comprar/hyundai~accent~2023~2d26",
        titulo="Hyundai Accent 1.4 HCI PLUS MT 2023",
        precio=Decimal("10790000"),
        marca="Hyundai",
        modelo="Accent",
        anio=2023,
        km=74701,
        fecha_publicacion="2026-02-25",
        disponible=True,
    )
    base.update(kw)
    return AvisoAuto(**base)


class TestUrlsDesdeSitemap:
    def test_extrae_solo_urls_de_comprar(self):
        urls = _urls_desde_sitemap(_SITEMAP_XML)
        assert urls == [
            "https://www.checkeados.cl/comprar/hyundai~accent~2023~2d26",
            "https://www.checkeados.cl/comprar/suzuki~swift~2025~2846",
        ]

    def test_sitemap_vacio(self):
        assert _urls_desde_sitemap("<urlset></urlset>") == []


class TestExtraerVehicle:
    def test_extrae_vehicle_del_next_data(self):
        html = _html_next_data_detalle(_vehicle_valido())
        vehicle = _extraer_vehicle(html)
        assert vehicle is not None
        assert vehicle["brand"] == "HYUNDAI"

    def test_sin_next_data_retorna_none(self):
        assert _extraer_vehicle("<html><body>nada</body></html>") is None

    def test_vehicle_none_retorna_none(self):
        html = _html_next_data_detalle(None)
        assert _extraer_vehicle(html) is None


class TestParsearVehicle:
    def test_parsea_vehicle_completo(self):
        url = "https://www.checkeados.cl/comprar/hyundai~accent~2023~2d26"
        aviso = _parsear_vehicle(_vehicle_valido(), url)
        assert aviso is not None
        assert aviso.fuente == "checkeados"
        assert aviso.marca == "Hyundai"
        assert aviso.modelo == "Accent"
        assert aviso.precio == Decimal("10790000")
        assert aviso.km == 74701
        assert aviso.anio == 2023
        assert aviso.combustible == "Bencina"
        assert aviso.ubicacion == "Movicenter"
        assert aviso.url_imagen == "https://d2k67dszumfzw5.cloudfront.net/production/x/1.png"
        assert aviso.fecha_publicacion == "2026-02-25"
        assert aviso.disponible is True

    def test_sin_id_retorna_none(self):
        vehicle = _vehicle_valido()
        del vehicle["id"]
        assert _parsear_vehicle(vehicle, "https://x.cl/comprar/a") is None

    def test_status_no_publicado_marca_no_disponible(self):
        aviso = _parsear_vehicle(_vehicle_valido(status="Vendido"), "https://x.cl/comprar/a")
        assert aviso is not None
        assert aviso.disponible is False

    def test_precio_cero_queda_none(self):
        aviso = _parsear_vehicle(_vehicle_valido(price=0), "https://x.cl/comprar/a")
        assert aviso is not None
        assert aviso.precio is None

    def test_fallback_a_images_si_no_hay_main_image(self):
        vehicle = _vehicle_valido(mainImageUrl="")
        aviso = _parsear_vehicle(vehicle, "https://x.cl/comprar/a")
        assert aviso is not None
        assert aviso.url_imagen == "https://d2k67dszumfzw5.cloudfront.net/production/x/1.png"


class TestValidacionCheckeados:
    """_validar_aviso: lista vacía = válido."""

    def test_aviso_valido(self):
        assert _validar_aviso(_aviso_valido()) == []

    def test_precio_bajo_minimo(self):
        errores = _validar_aviso(_aviso_valido(precio=Decimal("100000")))
        assert any("fuera de rango" in e for e in errores)

    def test_anio_sobre_rango(self):
        futuro = datetime.now().year + 5
        errores = _validar_aviso(_aviso_valido(anio=futuro))
        assert any("fuera de rango" in e for e in errores)

    def test_fecha_futura(self):
        manana = (datetime.now().date() + timedelta(days=1)).isoformat()
        errores = _validar_aviso(_aviso_valido(fecha_publicacion=manana))
        assert any("futura" in e for e in errores)


class TestScraperCheckeadosCloudIntegracion:
    """scrape() end-to-end con httpx mockeado (sin red, sin disco, sin S3)."""

    async def test_scrape_filtra_invalidos_y_deduplica(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        vehicle_barato = _vehicle_valido(id="v2", price=100000, brand="SUZUKI", model="SWIFT")

        async def _mock_get(url, headers=None, timeout=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.status_code = 200
            if "sitemap_catalog" in url:
                resp.text = _SITEMAP_XML
            elif "suzuki" in url:
                resp.text = _html_next_data_detalle(vehicle_barato)
            else:
                resp.text = _html_next_data_detalle(_vehicle_valido())
            return resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_mock_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "carflip.scrapers.Checkeados.checkeadosCloud.httpx.AsyncClient",
            return_value=mock_client,
        ):
            scraper = ScraperCheckeadosCloud(guardar_raw=False)
            avisos = await scraper.scrape()

        assert isinstance(avisos, list)
        assert all(isinstance(a, AvisoAuto) for a in avisos)
        # El aviso con precio $100.000 (bajo el mínimo) fue rechazado en validación
        assert len(avisos) == 1
        assert avisos[0].marca == "Hyundai"
        ids = [a.id_externo for a in avisos]
        assert len(ids) == len(set(ids))
