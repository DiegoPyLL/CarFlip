"""Tests para helpers compartidos de carflip.scrapers.base."""

from decimal import Decimal

from carflip.scrapers.base import (
    AvisoAuto,
    construir_id_externo,
    normalizar_url,
)


class TestNormalizarUrl:
    """normalizar_url quita query, fragmento y trailing slash."""

    def test_quita_query_y_fragmento(self):
        assert normalizar_url("https://x.cl/a/b?p=1#frag") == "https://x.cl/a/b"

    def test_quita_trailing_slash(self):
        assert normalizar_url("https://x.cl/a/b/") == "https://x.cl/a/b"

    def test_url_ya_canonica_no_cambia(self):
        assert normalizar_url("https://x.cl/a/b") == "https://x.cl/a/b"


class TestConstruirIdExterno:
    """construir_id_externo: SHA256 estable del URL canónico."""

    def test_determinista(self):
        url = "https://www.autocosmos.cl/auto/usado/ford/fiesta/12345"
        assert construir_id_externo(url) == construir_id_externo(url)

    def test_es_hash_sha256_hex(self):
        out = construir_id_externo("https://x.cl/a")
        assert len(out) == 64
        assert all(c in "0123456789abcdef" for c in out)

    def test_query_y_fragmento_no_afectan_id(self):
        base = "https://x.cl/auto/1"
        assert construir_id_externo(base) == construir_id_externo(base + "?utm=ads#top")

    def test_urls_distintas_ids_distintos(self):
        assert construir_id_externo("https://x.cl/a") != construir_id_externo("https://x.cl/b")


class TestNombreNormalizado:
    """AvisoAuto.nombre_normalizado arma un slug estable con hash del URL."""

    def _aviso(self, **kw) -> AvisoAuto:
        base = dict(
            fuente="autocosmos",
            id_externo="abc",
            url="https://x.cl/auto/1",
            titulo="t",
        )
        base.update(kw)
        return AvisoAuto(**base)

    def test_incluye_fuente_marca_modelo_anio(self):
        aviso = self._aviso(marca="Toyota", modelo="Corolla", anio=2020)
        nombre = aviso.nombre_normalizado
        assert nombre.startswith("autocosmos_toyota_corolla_2020_")
        # sufijo: hash de 8 caracteres hex
        sufijo = nombre.rsplit("_", 1)[-1]
        assert len(sufijo) == 8

    def test_omite_partes_ausentes(self):
        aviso = self._aviso(marca=None, modelo=None, anio=None)
        nombre = aviso.nombre_normalizado
        # solo fuente + hash
        assert nombre.startswith("autocosmos_")
        assert len(nombre.split("_")) == 2

    def test_slug_normaliza_espacios_y_mayusculas(self):
        aviso = self._aviso(marca="Land Rover", modelo="Range Rover", anio=2021)
        assert "land_rover" in aviso.nombre_normalizado
        assert "range_rover" in aviso.nombre_normalizado
