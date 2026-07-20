"""Tests del scraper Checkeados Cloud: parsers puros sobre el JSON de
/api/vehicles, construcción de la URL pública, validación, y un test de
integración de scrape() con httpx mockeado."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from carflip.scrapers.Checkeados.checkeadosCloud import (
    ScraperCheckeadosCloud,
    _parsear_vehicle,
    _url_detalle,
    _validar_aviso,
)
from carflip.scrapers.base import AvisoAuto


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


class TestUrlDetalle:
    def test_construye_url_publica(self):
        url = _url_detalle(_vehicle_valido())
        assert url == "https://www.checkeados.cl/comprar/hyundai~accent~2023~2d26"

    def test_codifica_espacios_y_usa_4_chars_del_id(self):
        vehicle = _vehicle_valido(
            id="9f8e7d6c-1111-2222-3333-444455556666",
            brand="LAND ROVER",
            model="RANGE ROVER EVOQUE",
            year=2020,
        )
        assert _url_detalle(vehicle) == (
            "https://www.checkeados.cl/comprar/land%20rover~range%20rover%20evoque~2020~9f8e"
        )


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
    """scrape() end-to-end con httpx mockeado (sin red, sin disco, sin R2)."""

    async def test_scrape_filtra_invalidos_y_deduplica(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        hyundai = _vehicle_valido()
        suzuki_barato = _vehicle_valido(
            id="a1b2c3d4-0000-1111-2222-333344445555",
            price=100000,
            brand="SUZUKI",
            model="SWIFT",
        )
        # El tercer vehicle repite el id del primero → misma URL → mismo id_externo
        vehiculos = [hyundai, suzuki_barato, dict(hyundai)]

        async def _mock_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.status_code = 200
            if url.endswith("/count"):
                resp.json = MagicMock(return_value=len(vehiculos))
            else:
                resp.json = MagicMock(return_value=vehiculos)
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

        assert all(isinstance(a, AvisoAuto) for a in avisos)
        # El duplicado cae en limpieza y el Suzuki a $100.000 en validación
        assert [a.marca for a in avisos] == ["Hyundai"]
        assert scraper.ultimo_reporte["avisos_encontrados"] == 3
        assert scraper.ultimo_reporte["avisos_unicos"] == 2
        assert scraper.ultimo_reporte["avisos_validos"] == 1
