"""Tests unitarios del detector — lógica de filtrado y lotes, sin BD."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from carflip.config import settings
from carflip.deals.detector import _lotes, _necesita_ia


def _previo(precio: Decimal | None, hace_dias: float):
    fecha = datetime.now(timezone.utc) - timedelta(days=hace_dias)
    return (precio, fecha)


class TestNecesitaIa:
    def test_candidato_nuevo_va_al_llm(self, hacer_candidato):
        assert _necesita_ia(hacer_candidato(), previos={}) is True

    def test_mismo_precio_y_reciente_no_va(self, hacer_candidato):
        c = hacer_candidato()
        previos = {(c.fuente, c.id_externo): _previo(c.precio, hace_dias=1)}
        assert _necesita_ia(c, previos) is False

    def test_precio_distinto_va(self, hacer_candidato):
        c = hacer_candidato()
        previos = {(c.fuente, c.id_externo): _previo(c.precio - Decimal("500000"), hace_dias=1)}
        assert _necesita_ia(c, previos) is True

    def test_categorizacion_vencida_va(self, hacer_candidato):
        c = hacer_candidato()
        vencido = settings.deal_recategorizar_dias + 1
        previos = {(c.fuente, c.id_externo): _previo(c.precio, hace_dias=vencido)}
        assert _necesita_ia(c, previos) is True

    def test_previo_sin_categorizar_va(self, hacer_candidato):
        c = hacer_candidato()
        previos = {(c.fuente, c.id_externo): (None, None)}
        assert _necesita_ia(c, previos) is True

    def test_misma_id_en_otra_fuente_no_cuenta(self, hacer_candidato):
        c = hacer_candidato(fuente="yapo")
        previos = {("autocosmos", c.id_externo): _previo(c.precio, hace_dias=1)}
        assert _necesita_ia(c, previos) is True


class TestLotes:
    def test_particion_exacta(self, hacer_candidato):
        items = [hacer_candidato(id_externo=str(i)) for i in range(20)]
        lotes = _lotes(items, 10)
        assert [len(l) for l in lotes] == [10, 10]

    def test_ultimo_lote_parcial(self, hacer_candidato):
        items = [hacer_candidato(id_externo=str(i)) for i in range(23)]
        lotes = _lotes(items, 10)
        assert [len(l) for l in lotes] == [10, 10, 3]
        assert lotes[-1][-1].id_externo == "22"

    def test_lista_vacia(self):
        assert _lotes([], 10) == []
