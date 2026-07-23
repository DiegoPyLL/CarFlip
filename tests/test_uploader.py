"""Tests de la subida de avisos a la base de datos (`upsert_avisos`).

El valor del uploader está en el SQL: el ON CONFLICT que detecta cambios de
precio y el loteo que respeta el límite de parámetros de Postgres. Nada de eso
se puede verificar con un mock, así que corren contra una BD real levantada
para el test. Ver `sesion_bd` en conftest.py.

Ejecutar con:
    CARFLIP_TEST_DATABASE_URL=postgresql+asyncpg://... pytest -m integration tests/test_uploader.py
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from carflip.database.models import AutocosmosListing
from carflip.database.uploader import _MAX_PARAMETROS_POSTGRES, upsert_avisos
from carflip.scrapers.base import AvisoAuto

from .conftest import requiere_bd


def _aviso(id_externo: str, precio: int | None = 8_500_000, **extra) -> AvisoAuto:
    base = {
        "fuente": "autocosmos",
        "id_externo": id_externo,
        "url": f"https://autocosmos.cl/aviso/{id_externo}",
        "titulo": f"Toyota Corolla 2020 {id_externo}",
        "precio": Decimal(precio) if precio is not None else None,
        "marca": "Toyota",
        "modelo": "Corolla",
        "anio": 2020,
        "km": 85_000,
        "disponible": True,
    }
    base.update(extra)
    return AvisoAuto(**base)


async def _columnas(sesion, *columnas, id_externo: str):
    fila = await sesion.execute(
        select(*columnas).where(AutocosmosListing.id_externo == id_externo)
    )
    return fila.one()


# ── Sin base de datos ────────────────────────────────────────────────────────


async def test_lista_vacia_no_ejecuta_sql():
    """Una corrida sin avisos no debe abrir transacción ni mandar statements."""
    sesion = AsyncMock()

    assert await upsert_avisos(sesion, [], AutocosmosListing) == 0
    sesion.execute.assert_not_called()
    sesion.commit.assert_not_called()


# ── Contra la base de datos ──────────────────────────────────────────────────


@requiere_bd
async def test_inserta_avisos_nuevos(sesion_bd):
    """Los avisos nuevos llegan completos a la tabla de la fuente."""
    n = await upsert_avisos(sesion_bd, [_aviso("a1"), _aviso("a2")], AutocosmosListing)

    assert n == 2
    titulo, precio, marca, km = await _columnas(
        sesion_bd,
        AutocosmosListing.titulo,
        AutocosmosListing.precio,
        AutocosmosListing.marca,
        AutocosmosListing.km,
        id_externo="a1",
    )
    assert titulo == "Toyota Corolla 2020 a1"
    assert precio == Decimal("8500000.00")
    assert marca == "Toyota"
    assert km == 85_000


@requiere_bd
async def test_deduplica_id_externo_repetido(sesion_bd):
    """Dos avisos con el mismo id_externo en la misma corrida no rompen el upsert.

    Postgres aborta un ON CONFLICT que toca la misma fila dos veces en un solo
    statement, así que la deduplicación previa no es cosmética: sin ella la
    corrida entera falla. Gana el primero que llegó.
    """
    avisos = [_aviso("dup", precio=8_000_000), _aviso("dup", precio=9_000_000)]

    n = await upsert_avisos(sesion_bd, avisos, AutocosmosListing)

    assert n == 1
    total = await sesion_bd.scalar(select(func.count()).select_from(AutocosmosListing))
    assert total == 1
    (precio,) = await _columnas(sesion_bd, AutocosmosListing.precio, id_externo="dup")
    assert precio == Decimal("8000000.00")


@requiere_bd
async def test_reejecutar_actualiza_sin_duplicar(sesion_bd):
    """Re-scrapear el mismo aviso actualiza la fila y refresca `ultima_vez_visto`."""
    await upsert_avisos(sesion_bd, [_aviso("a1", km=85_000)], AutocosmosListing)
    (visto_antes,) = await _columnas(
        sesion_bd, AutocosmosListing.ultima_vez_visto, id_externo="a1"
    )

    await upsert_avisos(
        sesion_bd, [_aviso("a1", km=91_000, ubicacion="Valparaíso")], AutocosmosListing
    )

    total = await sesion_bd.scalar(select(func.count()).select_from(AutocosmosListing))
    assert total == 1
    km, ubicacion, visto_despues = await _columnas(
        sesion_bd,
        AutocosmosListing.km,
        AutocosmosListing.ubicacion,
        AutocosmosListing.ultima_vez_visto,
        id_externo="a1",
    )
    assert km == 91_000
    assert ubicacion == "Valparaíso"
    assert visto_despues >= visto_antes


@requiere_bd
async def test_baja_de_precio_guarda_precio_anterior_y_delta(sesion_bd):
    """Una baja de $10M a $9M deja precio_anterior=10M y delta_pct=-10%.

    Es el dato que alimenta el badge de "bajó de precio" en la web: si el
    ON CONFLICT se calcula al revés, el sitio muestra alzas como bajas.
    """
    await upsert_avisos(sesion_bd, [_aviso("a1", precio=10_000_000)], AutocosmosListing)
    await upsert_avisos(sesion_bd, [_aviso("a1", precio=9_000_000)], AutocosmosListing)

    precio, anterior, delta = await _columnas(
        sesion_bd,
        AutocosmosListing.precio,
        AutocosmosListing.precio_anterior,
        AutocosmosListing.delta_pct,
        id_externo="a1",
    )
    assert precio == Decimal("9000000.00")
    assert anterior == Decimal("10000000.00")
    assert delta == pytest.approx(-10.0)


@requiere_bd
async def test_alza_de_precio_da_delta_positivo(sesion_bd):
    """El signo de delta_pct distingue alza de baja."""
    await upsert_avisos(sesion_bd, [_aviso("a1", precio=8_000_000)], AutocosmosListing)
    await upsert_avisos(sesion_bd, [_aviso("a1", precio=10_000_000)], AutocosmosListing)

    anterior, delta = await _columnas(
        sesion_bd,
        AutocosmosListing.precio_anterior,
        AutocosmosListing.delta_pct,
        id_externo="a1",
    )
    assert anterior == Decimal("8000000.00")
    assert delta == pytest.approx(25.0)


@requiere_bd
async def test_precio_sin_cambio_conserva_el_historial(sesion_bd):
    """Un scrape que no cambia el precio no puede borrar la baja anterior.

    El pipeline corre varias veces al día: si cada pasada pisara
    precio_anterior con el precio actual, el delta se perdería a las horas.
    """
    await upsert_avisos(sesion_bd, [_aviso("a1", precio=10_000_000)], AutocosmosListing)
    await upsert_avisos(sesion_bd, [_aviso("a1", precio=9_000_000)], AutocosmosListing)
    await upsert_avisos(sesion_bd, [_aviso("a1", precio=9_000_000)], AutocosmosListing)

    anterior, delta = await _columnas(
        sesion_bd,
        AutocosmosListing.precio_anterior,
        AutocosmosListing.delta_pct,
        id_externo="a1",
    )
    assert anterior == Decimal("10000000.00")
    assert delta == pytest.approx(-10.0)


@requiere_bd
async def test_primera_carga_no_inventa_delta(sesion_bd):
    """Un aviso recién visto no tiene precio anterior contra el cual comparar."""
    await upsert_avisos(sesion_bd, [_aviso("a1")], AutocosmosListing)

    anterior, delta = await _columnas(
        sesion_bd,
        AutocosmosListing.precio_anterior,
        AutocosmosListing.delta_pct,
        id_externo="a1",
    )
    assert anterior is None
    assert delta is None


@requiere_bd
async def test_corrida_grande_respeta_el_limite_de_parametros(sesion_bd):
    """Una corrida más grande que un solo statement se sube igual, en lotes.

    asyncpg corta en 32767 parámetros bindeados; con 15 columnas eso son ~2184
    filas. Sin loteo, una corrida real de Autocosmos revienta la subida entera.
    """
    filas_por_lote = _MAX_PARAMETROS_POSTGRES // 15
    avisos = [_aviso(f"masivo-{i}") for i in range(filas_por_lote + 50)]

    n = await upsert_avisos(sesion_bd, avisos, AutocosmosListing)

    assert n == len(avisos)
    total = await sesion_bd.scalar(select(func.count()).select_from(AutocosmosListing))
    assert total == len(avisos)
