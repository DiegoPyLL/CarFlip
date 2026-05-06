"""Tests para parseo de precios y km en los scrapers httpx."""

from decimal import Decimal

from carflip.scrapers.autosusados import _parse_price, _parse_km


def test_parse_price_clp():
    assert _parse_price("$ 8.500.000") == Decimal("8500000")


def test_parse_price_without_symbol():
    assert _parse_price("12.300.000") == Decimal("12300000")


def test_parse_price_empty():
    assert _parse_price("") is None


def test_parse_price_text_only():
    assert _parse_price("Precio a convenir") is None


def test_parse_km_normal():
    assert _parse_km("85.000 km") == 85000


def test_parse_km_no_separator():
    assert _parse_km("120000km") == 120000


def test_parse_km_empty():
    assert _parse_km("") is None
