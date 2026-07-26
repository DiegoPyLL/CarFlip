"""Tests para helpers compartidos de carflip.scrapers.base."""

from decimal import Decimal

from carflip.scrapers.base import (
    AvisoAuto,
    construir_id_externo,
    normalizar_traccion,
    normalizar_transmision,
    normalizar_url,
    traccion_desde_texto,
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


class TestNormalizarTransmision:
    """normalizar_transmision canoniza a 'Manual'/'Automática' o None."""

    def test_variantes_automatica(self):
        for texto in ["Automática", "automatica", "AUTOMATICO", "CVT", "DSG", "A/T", "Tiptronic"]:
            assert normalizar_transmision(texto) == "Automática", texto

    def test_variantes_manual(self):
        # "Mecánica" es el uso chileno para manual.
        for texto in ["Manual", "Mecánica", "mecanica", "M/T", "MT"]:
            assert normalizar_transmision(texto) == "Manual", texto

    def test_titulo_tipo_ficha(self):
        # Autosusados publica la ficha en el título: "…DIESEL 4X2 AT8 5P".
        assert normalizar_transmision("OPEL GRANDLAND 1.5 GS LINE DIESEL 4X2 AT8 5P") == "Automática"
        assert normalizar_transmision("SUZUKI SWIFT 1.2 GL MT 5P") == "Manual"

    def test_irreconocible_o_vacio_es_none(self):
        assert normalizar_transmision("otra cosa") is None
        assert normalizar_transmision("") is None
        assert normalizar_transmision(None) is None


class TestNormalizarTraccion:
    """normalizar_traccion canoniza valores explícitos; '4x2' no dice qué eje."""

    def test_variantes_4x4(self):
        for texto in ["4x4", "4X4", "AWD", "4WD", "Tracción integral"]:
            assert normalizar_traccion(texto) == "4x4", texto

    def test_delantera_y_trasera(self):
        assert normalizar_traccion("Delantera") == "Delantera"
        assert normalizar_traccion("FWD") == "Delantera"
        assert normalizar_traccion("Trasera") == "Trasera"
        assert normalizar_traccion("RWD") == "Trasera"

    def test_4x2_no_se_mapea(self):
        assert normalizar_traccion("4x2") is None
        assert normalizar_traccion(None) is None


class TestTraccionDesdeTexto:
    """traccion_desde_texto: solo menciones inequívocas en título/descripción."""

    def test_ficha_con_4x4(self):
        assert traccion_desde_texto("TOYOTA HILUX 2.8 SR 4X4 AT 4P") == "4x4"

    def test_traccion_explicita_en_descripcion(self):
        assert traccion_desde_texto(None, "Full equipo, tracción delantera, único dueño") == "Delantera"

    def test_palabra_suelta_no_cuenta(self):
        # "cámara delantera" no es tracción.
        assert traccion_desde_texto("Sedán full", "cámara delantera y sensores") is None

    def test_prioriza_4x4_sobre_otras_menciones(self):
        assert traccion_desde_texto("Jeep 4x4 con tracción delantera desconectable") == "4x4"
