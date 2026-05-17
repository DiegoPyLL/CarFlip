"""Tests para parseo de precios y km en el scraper de Autocosmos."""

from decimal import Decimal

from carflip.scrapers.AutoCosmos.autocosmos import AutocosmosClient


def test_parsear_precio_clp():
    assert AutocosmosClient._parsear_precio("$ 8.500.000") == Decimal("8500000")


def test_parsear_precio_sin_espacios():
    assert AutocosmosClient._parsear_precio("$12.300.000") == Decimal("12300000")


def test_parsear_precio_vacio():
    assert AutocosmosClient._parsear_precio("") is None


def test_parsear_precio_texto():
    assert AutocosmosClient._parsear_precio("Precio a convenir") is None


def test_parsear_km_normal():
    assert AutocosmosClient._parsear_km("85.000 km") == 85000


def test_parsear_km_sin_separador():
    assert AutocosmosClient._parsear_km("120000km") == 120000


def test_parsear_km_vacio():
    assert AutocosmosClient._parsear_km("") is None
