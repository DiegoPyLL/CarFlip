"""Tests unitarios para la lógica de price tracking."""

from decimal import Decimal

import pytest

from carflip.database.price_tracker import _delta_pct


def test_delta_pct_price_drop():
    assert _delta_pct(Decimal("10000000"), Decimal("8000000")) == pytest.approx(-20.0)


def test_delta_pct_price_increase():
    assert _delta_pct(Decimal("5000000"), Decimal("6000000")) == pytest.approx(20.0)


def test_delta_pct_no_change():
    assert _delta_pct(Decimal("5000000"), Decimal("5000000")) == pytest.approx(0.0)


def test_delta_pct_from_zero():
    assert _delta_pct(None, Decimal("5000000")) == 0.0


def test_delta_pct_small_drop():
    result = _delta_pct(Decimal("12000000"), Decimal("11500000"))
    assert result == pytest.approx(-4.166, rel=1e-2)
