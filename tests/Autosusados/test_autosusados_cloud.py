"""Tests del scraper Autosusados Cloud: parsers puros sobre el JSON __NEXT_DATA__,
validación, y un test de integración de scrape() con httpx mockeado."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from carflip.scrapers.Autosusados.autosusadosCloud import (
    ScraperAutosusadosCloud,
    _extraer_posts,
    _parsear_post,
    _url_detalle,
    _validar_aviso,
)
from carflip.scrapers.base import AvisoAuto


def _post_valido(**kw) -> dict:
    base = dict(
        carID=1279403,
        categoryID=3,
        brandID=48,
        brandName="OPEL",
        modelID=3370,
        modelName="GRANDLAND",
        description="OPEL GRANDLAND 1.5 GS LINE DIESEL 4X2 AT8 5P",
        year=2023,
        price=16290000,
        currency="$",
        kilometers=49500,
        fuelID=2,
        fuelName="Diésel",
        region=13,
        photo="https://storage.googleapis.com/fotosautos/opel.webp",
        table=1,
        total=7877,
    )
    base.update(kw)
    return base


def _html_next_data(posts) -> str:
    data = {"props": {"pageProps": {"vechicleType": {"name": "vehiculos", "id": None}, "initialPosts": posts}}}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


def _aviso_valido(**kw) -> AvisoAuto:
    base = dict(
        fuente="autosusados",
        id_externo="abc123",
        url="https://autosusados.cl/suv/OPEL/GRANDLAND/1/1279403",
        titulo="OPEL GRANDLAND 1.5 GS LINE DIESEL 4X2 AT8 5P",
        precio=Decimal("16290000"),
        marca="Opel",
        modelo="Grandland",
        anio=2023,
        km=49500,
        fecha_publicacion="2020-01-15",
        disponible=True,
    )
    base.update(kw)
    return AvisoAuto(**base)


class TestExtraerPosts:
    def test_extrae_lista_de_posts(self):
        html = _html_next_data([_post_valido()])
        posts = _extraer_posts(html)
        assert isinstance(posts, list)
        assert len(posts) == 1
        assert posts[0]["carID"] == 1279403

    def test_extrae_error_de_rate_limit(self):
        data = {"props": {"pageProps": {"vechicleType": {}, "initialPosts": {"error": {"code": 429}}}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        posts = _extraer_posts(html)
        assert isinstance(posts, dict)
        assert posts["error"]["code"] == 429

    def test_sin_next_data_retorna_none(self):
        assert _extraer_posts("<html><body>nada</body></html>") is None


class TestUrlDetalle:
    def test_construye_url_suv(self):
        url = _url_detalle(_post_valido())
        assert url == "https://autosusados.cl/suv/OPEL/GRANDLAND/1/1279403"

    def test_categoria_desconocida_usa_default_autos(self):
        url = _url_detalle(_post_valido(categoryID=999))
        assert url.startswith("https://autosusados.cl/autos/")


class TestParsearPost:
    def test_parsea_post_completo(self):
        aviso = _parsear_post(_post_valido())
        assert aviso is not None
        assert aviso.fuente == "autosusados"
        assert aviso.marca == "Opel"
        assert aviso.modelo == "Grandland"
        assert aviso.precio == Decimal("16290000")
        assert aviso.km == 49500
        assert aviso.anio == 2023
        assert aviso.combustible == "Diésel"
        assert aviso.ubicacion == "Metropolitana"
        assert aviso.url_imagen == "https://storage.googleapis.com/fotosautos/opel.webp"
        assert aviso.disponible is True

    def test_sin_car_id_retorna_none(self):
        post = _post_valido()
        del post["carID"]
        assert _parsear_post(post) is None

    def test_precio_cero_o_negativo_queda_none(self):
        aviso = _parsear_post(_post_valido(price=0))
        assert aviso is not None
        assert aviso.precio is None

    def test_region_desconocida_queda_none(self):
        aviso = _parsear_post(_post_valido(region=999))
        assert aviso is not None
        assert aviso.ubicacion is None


class TestValidacionAutosusados:
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


class TestScraperAutosusadosCloudIntegracion:
    """scrape() end-to-end con httpx mockeado (sin red, sin disco, sin S3)."""

    async def test_scrape_filtra_invalidos_y_deduplica(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        pagina_1 = [
            _post_valido(carID=1, price=16290000),
            _post_valido(carID=2, price=8000000, brandName="TOYOTA", modelName="COROLLA"),
            _post_valido(carID=3, price=100000),  # bajo el mínimo → rechazado en validación
        ]

        async def _mock_get(url, params=None, headers=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            pagina = params.get("page", 1) if params else 1
            if pagina == 1:
                resp.text = _html_next_data(pagina_1)
            else:
                resp.text = _html_next_data([])  # fin de paginación
            return resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_mock_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "carflip.scrapers.Autosusados.autosusadosCloud.httpx.AsyncClient",
            return_value=mock_client,
        ):
            scraper = ScraperAutosusadosCloud(max_paginas=1, guardar_raw=False)
            avisos = await scraper.scrape()

        assert isinstance(avisos, list)
        assert all(isinstance(a, AvisoAuto) for a in avisos)
        assert len(avisos) == 2
        ids = [a.id_externo for a in avisos]
        assert len(ids) == len(set(ids))
        assert all(a.precio is not None and a.precio >= Decimal("500000") for a in avisos)

    async def test_pagina_avanza_y_acumula_avisos_de_varias_paginas(self, monkeypatch, tmp_path):
        """El sitio pagina con ?page=N: un nombre de parámetro equivocado hace que
        el servidor devuelva siempre la página 1, y la paginación corta al primer
        lote por 'sin avisos nuevos'. Este test falla si se vuelve a usar ?pagina=N."""
        monkeypatch.chdir(tmp_path)

        paginas = {
            1: [_post_valido(carID=1), _post_valido(carID=2)],
            2: [_post_valido(carID=3), _post_valido(carID=4)],
            3: [_post_valido(carID=5), _post_valido(carID=6)],
        }
        params_vistos: list[dict] = []

        async def _mock_get(url, params=None, headers=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            params_vistos.append(dict(params or {}))
            # El servidor solo entiende `page`; cualquier otro nombre → página 1
            pagina = (params or {}).get("page", 1)
            resp.text = _html_next_data(paginas.get(pagina, []))
            return resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=_mock_get)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "carflip.scrapers.Autosusados.autosusadosCloud.httpx.AsyncClient",
            return_value=mock_client,
        ):
            scraper = ScraperAutosusadosCloud(max_paginas=3, guardar_raw=False)
            avisos = await scraper.scrape()

        assert all("page" in p for p in params_vistos), f"params usados: {params_vistos}"
        assert {p["page"] for p in params_vistos} >= {1, 2, 3}
        assert len(avisos) == 6
