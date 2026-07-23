"""Tests del snapshot diario de mercado (`snapshot_market`).

Los agregados que grafica /mercado se calculan enteramente en SQL sobre la
unión de las cinco fuentes, así que la verificación honesta es sembrar avisos
con valores conocidos en una BD real y comparar la fila resultante.

Ejecutar con:
    CARFLIP_TEST_DATABASE_URL=postgresql+asyncpg://... pytest -m integration tests/test_snapshot.py
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from carflip.database.models import (
    AutocosmosListing,
    CheckeadosListing,
    MarketSnapshot,
    ParticularListing,
    Perfil,
    YapoListing,
)
from carflip.database.snapshot import snapshot_market

from .conftest import requiere_bd


def _listing(modelo, id_externo: str, precio: int | None, **extra):
    base = {
        "id_externo": id_externo,
        "url": f"https://ejemplo.cl/{id_externo}",
        "titulo": f"Aviso {id_externo}",
        "precio": Decimal(precio) if precio is not None else None,
        "marca": "Toyota",
        "disponible": True,
    }
    base.update(extra)
    return modelo(**base)


async def _sembrar_particular(sesion, id_externo: str, precio: int, estado: str):
    """Un aviso de particular necesita perfil dueño: la FK no es opcional."""
    usuario_id = uuid.uuid4()
    sesion.add(Perfil(id=usuario_id))
    await sesion.flush()
    sesion.add(
        _listing(
            ParticularListing,
            id_externo,
            precio,
            usuario_id=usuario_id,
            estado=estado,
        )
    )


async def _fila_snapshot(sesion) -> MarketSnapshot:
    return await sesion.scalar(select(MarketSnapshot))


@requiere_bd
async def test_suma_las_cinco_fuentes(sesion_bd):
    """El total y `por_fuente` cubren las cinco fuentes de avisos."""
    sesion_bd.add(_listing(AutocosmosListing, "ac-1", 8_000_000))
    sesion_bd.add(_listing(AutocosmosListing, "ac-2", 9_000_000))
    sesion_bd.add(_listing(YapoListing, "yp-1", 7_000_000))
    sesion_bd.add(_listing(CheckeadosListing, "ch-1", 11_000_000))
    await _sembrar_particular(sesion_bd, "pa-1", 10_000_000, "publicado")
    await sesion_bd.commit()

    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    assert fila.total == 5
    assert fila.por_fuente == {
        "autocosmos": 2,
        "yapo": 1,
        "checkeados": 1,
        "particular": 1,
    }


@requiere_bd
async def test_excluye_particulares_no_publicados(sesion_bd):
    """Un aviso pausado o vendido no es oferta vigente: no entra en el mercado."""
    await _sembrar_particular(sesion_bd, "pa-ok", 10_000_000, "publicado")
    await _sembrar_particular(sesion_bd, "pa-pausado", 10_000_000, "pausado")
    await _sembrar_particular(sesion_bd, "pa-vendido", 10_000_000, "vendido")
    await sesion_bd.commit()

    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    assert fila.total == 1
    assert fila.por_fuente == {"particular": 1}


@requiere_bd
async def test_percentiles_y_promedio(sesion_bd):
    """Con 6M/8M/10M/12M/14M la mediana es 10M, p25 8M, p75 12M y el promedio 10M."""
    for i, precio in enumerate([6_000_000, 8_000_000, 10_000_000, 12_000_000, 14_000_000]):
        sesion_bd.add(_listing(AutocosmosListing, f"ac-{i}", precio))
    await sesion_bd.commit()

    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    assert fila.precio_mediano == Decimal("10000000.00")
    assert fila.precio_p25 == Decimal("8000000.00")
    assert fila.precio_p75 == Decimal("12000000.00")
    assert fila.precio_promedio == Decimal("10000000.00")


@requiere_bd
async def test_ignora_precios_no_positivos_en_los_percentiles(sesion_bd):
    """Un aviso sin precio o en cero no puede arrastrar la mediana del mercado."""
    sesion_bd.add(_listing(AutocosmosListing, "ac-sin-precio", None))
    sesion_bd.add(_listing(AutocosmosListing, "ac-cero", 0))
    sesion_bd.add(_listing(AutocosmosListing, "ac-1", 10_000_000))
    await sesion_bd.commit()

    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    assert fila.total == 3, "el conteo sí incluye los avisos sin precio"
    assert fila.precio_mediano == Decimal("10000000.00")


@requiere_bd
async def test_cuenta_bajas_de_precio(sesion_bd):
    """`con_baja` cuenta solo los avisos cuyo último cambio fue a la baja."""
    sesion_bd.add(_listing(AutocosmosListing, "baja-1", 8_000_000, delta_pct=-12.5))
    sesion_bd.add(_listing(AutocosmosListing, "baja-2", 9_000_000, delta_pct=-3.0))
    sesion_bd.add(_listing(AutocosmosListing, "alza", 9_000_000, delta_pct=7.0))
    sesion_bd.add(_listing(AutocosmosListing, "sin-cambio", 9_000_000))
    await sesion_bd.commit()

    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    assert fila.con_baja == 2


@requiere_bd
async def test_nuevos_24h_solo_cuenta_los_recientes(sesion_bd):
    """Un aviso visto por primera vez hace tres días ya no es novedad."""
    hace_tres_dias = datetime.now(timezone.utc) - timedelta(days=3)
    sesion_bd.add(_listing(AutocosmosListing, "nuevo", 8_000_000))
    sesion_bd.add(
        _listing(AutocosmosListing, "viejo", 8_000_000, primera_vez_visto=hace_tres_dias)
    )
    await sesion_bd.commit()

    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    assert fila.total == 2
    assert fila.nuevos_24h == 1


@requiere_bd
async def test_payload_trae_top_marcas_ordenadas(sesion_bd):
    """El payload guarda las marcas por volumen, con su mediana como float JSON."""
    for i in range(3):
        sesion_bd.add(_listing(AutocosmosListing, f"toyota-{i}", 10_000_000))
    sesion_bd.add(_listing(AutocosmosListing, "kia-1", 6_000_000, marca="Kia"))
    await sesion_bd.commit()

    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    top = fila.payload["top_marcas"]
    assert [m["marca"] for m in top] == ["Toyota", "Kia"]
    assert top[0]["total"] == 3
    assert top[0]["mediana"] == 10_000_000.0
    assert isinstance(top[0]["mediana"], float), "Decimal no es serializable a JSONB"


@requiere_bd
async def test_reejecutar_el_mismo_dia_actualiza_la_fila(sesion_bd):
    """El workflow corre varias veces al día: debe actualizar, no duplicar."""
    sesion_bd.add(_listing(AutocosmosListing, "ac-1", 8_000_000))
    await sesion_bd.commit()
    fecha = await snapshot_market(sesion_bd)

    sesion_bd.add(_listing(AutocosmosListing, "ac-2", 12_000_000))
    await sesion_bd.commit()
    assert await snapshot_market(sesion_bd) == fecha

    total_filas = await sesion_bd.scalar(select(func.count()).select_from(MarketSnapshot))
    assert total_filas == 1
    sesion_bd.expire_all()
    fila = await _fila_snapshot(sesion_bd)
    assert fila.total == 2
    assert fila.precio_promedio == Decimal("10000000.00")


@requiere_bd
async def test_mercado_vacio_no_revienta(sesion_bd):
    """Sin avisos el snapshot se escribe igual, con totales en cero y precios nulos.

    Importa porque la primera corrida de un entorno nuevo pasa por aquí, y
    porque /mercado tiene que poder renderizar el día sin datos.
    """
    await snapshot_market(sesion_bd)

    fila = await _fila_snapshot(sesion_bd)
    assert fila.total == 0
    assert fila.nuevos_24h == 0
    assert fila.con_baja == 0
    assert fila.precio_mediano is None
    assert fila.por_fuente == {}
    assert fila.payload == {"top_marcas": []}
