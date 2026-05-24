"""Tests para carflip.database.price_tracker._delta_pct."""

from decimal import Decimal

import pytest

from carflip.database.price_tracker import _delta_pct


class TestDeltaPct:
    """_delta_pct: variación porcentual del precio (negativo = bajó)."""

    def test_subida(self):
        assert _delta_pct(Decimal("100"), Decimal("150")) == pytest.approx(50.0)

    def test_bajada(self):
        assert _delta_pct(Decimal("100"), Decimal("80")) == pytest.approx(-20.0)

    def test_sin_cambio(self):
        assert _delta_pct(Decimal("100"), Decimal("100")) == pytest.approx(0.0)

    def test_old_none_retorna_cero(self):
        assert _delta_pct(None, Decimal("100")) == 0.0

    def test_old_cero_retorna_cero(self):
        assert _delta_pct(Decimal("0"), Decimal("100")) == 0.0
