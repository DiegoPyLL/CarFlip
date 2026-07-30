from decimal import Decimal

import pytest

from carflip.deals.tipos import CandidatoDeal


@pytest.fixture
def hacer_candidato():
    """Factory de CandidatoDeal con valores razonables por defecto."""

    def _hacer(**kwargs) -> CandidatoDeal:
        base = {
            "fuente": "particular",
            "id_externo": "abc123",
            "url": "https://carflip.cl/auto/p/123",
            "titulo": "Toyota Yaris 2019",
            "precio": Decimal("6500000"),
            "marca": "Toyota",
            "modelo": "Yaris",
            "anio": 2019,
            "km": 78000,
            "descripcion": "Auto en excelente estado, mantenciones al día.",
            "precio_mercado": Decimal("9200000"),
            "comparables": 12,
            "pct_vs_mercado": -29.3,
        }
        base.update(kwargs)
        return CandidatoDeal(**base)

    return _hacer
