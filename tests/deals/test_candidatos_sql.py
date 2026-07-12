"""Test de integración de candidatos.sql contra una BD real.

Requiere una base de datos de test (no mockeamos la BD, según convención).
Se activa exportando CARFLIP_TEST_DATABASE_URL, por ejemplo:

    CARFLIP_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/carflip_test

Siembra un grupo de 6 comparables (~$10M) + 1 outlier ($6.5M, -35%)
+ 1 barato con km altísimo (excluido por el guard de km) y verifica
que la query retorna exactamente el outlier.
"""

import os
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from carflip.database.models import AutocosmosListing, Base
from carflip.deals.detector import _obtener_candidatos

_URL_BD_TEST = os.environ.get("CARFLIP_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _URL_BD_TEST,
        reason="requiere CARFLIP_TEST_DATABASE_URL apuntando a una BD de test",
    ),
]


def _aviso(id_externo: str, precio: int, km: int = 60000) -> AutocosmosListing:
    return AutocosmosListing(
        id_externo=id_externo,
        url=f"https://autocosmos.cl/aviso/{id_externo}",
        titulo=f"Toyota Yaris 2019 {id_externo}",
        precio=Decimal(precio),
        marca="Toyota",
        modelo="Yaris",
        anio=2019,
        km=km,
        disponible=True,
    )


async def test_query_detecta_outlier_y_excluye_km_alto():
    engine = create_async_engine(_URL_BD_TEST)
    sesion_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with sesion_local() as session:
        await session.execute(delete(AutocosmosListing))

        # Grupo comparable: 6 avisos alrededor de $10M
        for i, precio in enumerate([9_800_000, 10_000_000, 10_200_000, 9_900_000, 10_100_000, 10_500_000]):
            session.add(_aviso(f"comparable-{i}", precio))
        # Outlier real: 35% bajo la mediana, km normal
        session.add(_aviso("outlier", 6_500_000))
        # Barato pero con km altísimo → excluido por el guard (km > 1.5 × mediana)
        session.add(_aviso("km-alto", 6_500_000, km=250_000))
        await session.commit()

        candidatos = await _obtener_candidatos(session)

    await engine.dispose()

    ids = {c.id_externo for c in candidatos}
    assert "outlier" in ids
    assert "km-alto" not in ids
    outlier = next(c for c in candidatos if c.id_externo == "outlier")
    assert outlier.fuente == "autocosmos"
    assert outlier.precio_mercado is not None
    assert outlier.pct_vs_mercado is not None and outlier.pct_vs_mercado < -15
    assert outlier.comparables is not None and outlier.comparables >= 6
