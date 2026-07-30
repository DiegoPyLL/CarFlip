"""Test de integración de candidatos.sql contra una BD real.

Requiere una base de datos de test (no mockeamos la BD, según convención).
Se activa exportando CARFLIP_TEST_DATABASE_URL, por ejemplo:

    CARFLIP_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/carflip_test

Todos los avisos son de particulares: es la única fuente que llena el catálogo
desde que se retiraron los scrapers.
"""

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from carflip.config import settings
from carflip.database.models import Base, ParticularListing, Perfil
from carflip.deals.detector import _obtener_candidatos

_URL_BD_TEST = os.environ.get("CARFLIP_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _URL_BD_TEST,
        reason="requiere CARFLIP_TEST_DATABASE_URL apuntando a una BD de test",
    ),
]

# Precios de un grupo comparable alrededor de $10M, tantos como exige
# `deal_min_comparables`: con menos, `grupos` los descarta por el HAVING y no
# hay mediana contra la que medir al outlier.
_PRECIOS_COMPARABLES = [
    9_800_000, 10_000_000, 10_200_000, 9_900_000, 10_100_000, 10_500_000,
    9_700_000, 10_300_000, 9_950_000, 10_050_000, 9_850_000, 10_150_000,
    9_750_000, 10_250_000, 9_900_000, 10_000_000,
][: max(settings.deal_min_comparables, 6)]


def _aviso(
    perfil_id: uuid.UUID,
    id_externo: str,
    precio: int,
    km: int = 60000,
    visible: bool = True,
) -> ParticularListing:
    return ParticularListing(
        id_externo=id_externo,
        url=f"https://carflip.cl/auto/p/{id_externo}",
        titulo=f"Toyota Yaris 2019 {id_externo}",
        precio=Decimal(precio),
        marca="Toyota",
        modelo="Yaris",
        anio=2019,
        km=km,
        usuario_id=perfil_id,
        estado="publicado",
        visible_en_deals=visible,
        disponible=True,
    )


async def _limpiar(session) -> None:
    await session.execute(delete(ParticularListing))
    await session.execute(delete(Perfil))
    await session.commit()


async def test_query_detecta_outlier_y_excluye_km_alto():
    engine = create_async_engine(_URL_BD_TEST)
    sesion_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    perfil_id = uuid.uuid4()

    async with sesion_local() as session:
        await _limpiar(session)
        session.add(Perfil(id=perfil_id))
        await session.flush()

        for i, precio in enumerate(_PRECIOS_COMPARABLES):
            session.add(_aviso(perfil_id, f"comparable-{i}", precio))
        # Outlier real: 35% bajo la mediana, km normal
        session.add(_aviso(perfil_id, "outlier", 6_500_000))
        # Barato pero con km altísimo → excluido por el guard (km > 1.5 × mediana)
        session.add(_aviso(perfil_id, "km-alto", 6_500_000, km=250_000))
        await session.commit()

        candidatos = await _obtener_candidatos(session)
        await _limpiar(session)

    await engine.dispose()

    ids = {c.id_externo for c in candidatos}
    assert "outlier" in ids
    assert "km-alto" not in ids
    outlier = next(c for c in candidatos if c.id_externo == "outlier")
    assert outlier.fuente == "particular"
    assert outlier.precio_mercado is not None
    assert outlier.pct_vs_mercado is not None and outlier.pct_vs_mercado < -15
    assert outlier.comparables is not None
    assert outlier.comparables >= settings.deal_min_comparables


async def test_opt_out_no_es_candidato():
    """Dos avisos outlier idénticos salvo `visible_en_deals`: solo el que lo tiene
    activo entra a Deals; el opt-out queda fuera del pipeline (y del LLM).
    """
    engine = create_async_engine(_URL_BD_TEST)
    sesion_local = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    perfil_id = uuid.uuid4()

    async with sesion_local() as session:
        await _limpiar(session)
        session.add(Perfil(id=perfil_id))
        await session.flush()

        for i, precio in enumerate(_PRECIOS_COMPARABLES):
            session.add(_aviso(perfil_id, f"comp-{i}", precio))

        # Mismo outlier (-35%), la única diferencia es el flag de Deals.
        session.add(_aviso(perfil_id, "visible", 6_500_000, visible=True))
        session.add(_aviso(perfil_id, "oculto", 6_500_000, visible=False))
        await session.commit()

        candidatos = await _obtener_candidatos(session)
        await _limpiar(session)

    await engine.dispose()

    ids = {c.id_externo for c in candidatos}
    assert "visible" in ids
    assert "oculto" not in ids
