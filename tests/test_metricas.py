"""Tests de la persistencia de métricas de corrida (`guardar_run_report`).

El pipeline Cloud sube un run_report.json por fuente y esta función lo vuelca a
scrape_runs + run_fail_logs. Lo que importa verificar es que el upsert sea
idempotente sobre (source, started_at) —el workflow puede reprocesar el mismo
reporte— y que un reporte malformado no tumbe la corrida.

Ejecutar con:
    CARFLIP_TEST_DATABASE_URL=postgresql+asyncpg://... pytest -m integration tests/test_metricas.py
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from carflip.database.metricas import _parsear_fecha, guardar_run_report
from carflip.database.models import RunFailLog, ScrapedRun

from .conftest import requiere_bd

_TIMESTAMP = "2026-07-23T10:00:00+00:00"


def _reporte(**extra) -> dict:
    base = {
        "fuente": "autocosmos",
        "timestamp": _TIMESTAMP,
        "duracion_segundos": 125.5,
        "paginas_procesadas": 40,
        "avisos_encontrados": 1200,
        "avisos_unicos": 1150,
        "avisos_validos": 1100,
        "avisos_rechazados": 50,
        "fail_logs": [],
    }
    base.update(extra)
    return base


def _fail_log(**extra) -> dict:
    base = {
        "fuente": "autocosmos",
        "etapa": "parseo",
        "motivo": "precio bajo el mínimo",
        "id_externo": "abc123",
        "timestamp": _TIMESTAMP,
    }
    base.update(extra)
    return base


async def _contar(sesion, modelo) -> int:
    return await sesion.scalar(select(func.count()).select_from(modelo))


# ── Sin base de datos ────────────────────────────────────────────────────────


def test_fecha_naive_se_interpreta_como_utc():
    """Los reportes del pipeline vienen sin zona: asumir UTC evita saltos de 4 horas."""
    fecha = _parsear_fecha("2026-07-23T10:00:00")

    assert fecha == datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("valor", ["", None, "ayer", "2026-13-45"])
def test_fecha_invalida_no_lanza(valor):
    """Un timestamp corrupto se descarta en silencio, no rompe la subida."""
    assert _parsear_fecha(valor) is None


# ── Contra la base de datos ──────────────────────────────────────────────────


@requiere_bd
async def test_guarda_la_corrida_completa(sesion_bd):
    """Todas las métricas del reporte quedan en scrape_runs."""
    run_id = await guardar_run_report(sesion_bd, _reporte())

    assert run_id is not None
    run = await sesion_bd.get(ScrapedRun, run_id)
    assert run.source == "autocosmos"
    assert run.avisos_encontrados == 1200
    assert run.avisos_validos == 1100
    assert run.avisos_rechazados == 50
    assert run.paginas_procesadas == 40
    assert run.duracion_segundos == pytest.approx(125.5)


@requiere_bd
async def test_finished_at_se_deriva_de_la_duracion(sesion_bd):
    """El fin de la corrida se calcula, no se reporta: inicio + duración."""
    run_id = await guardar_run_report(sesion_bd, _reporte(duracion_segundos=60))

    run = await sesion_bd.get(ScrapedRun, run_id)
    assert (run.finished_at - run.started_at).total_seconds() == pytest.approx(60)


@requiere_bd
async def test_sin_duracion_no_hay_fin(sesion_bd):
    """Una corrida abortada sin duración deja finished_at nulo, no inventado."""
    run_id = await guardar_run_report(sesion_bd, _reporte(duracion_segundos=None))

    run = await sesion_bd.get(ScrapedRun, run_id)
    assert run.finished_at is None


@requiere_bd
async def test_guarda_los_fail_logs_asociados(sesion_bd):
    """Cada FAIL LOG del reporte queda colgando de su corrida."""
    reporte = _reporte(fail_logs=[_fail_log(), _fail_log(id_externo="def456")])

    run_id = await guardar_run_report(sesion_bd, reporte)

    run = await sesion_bd.get(ScrapedRun, run_id)
    assert run.errors == 2
    fails = (await sesion_bd.scalars(select(RunFailLog))).all()
    assert len(fails) == 2
    assert {f.run_id for f in fails} == {run_id}
    assert fails[0].etapa == "parseo"
    assert fails[0].motivo == "precio bajo el mínimo"


@requiere_bd
async def test_reprocesar_el_mismo_reporte_no_duplica(sesion_bd):
    """La clave natural es (source, started_at): recargar actualiza la misma fila."""
    primero = await guardar_run_report(sesion_bd, _reporte(avisos_validos=1100))
    segundo = await guardar_run_report(sesion_bd, _reporte(avisos_validos=1180))

    assert primero == segundo
    assert await _contar(sesion_bd, ScrapedRun) == 1
    sesion_bd.expire_all()
    run = await sesion_bd.get(ScrapedRun, primero)
    assert run.avisos_validos == 1180


@requiere_bd
async def test_reprocesar_reemplaza_los_fail_logs(sesion_bd):
    """Los FAIL LOGs se reemplazan enteros, no se acumulan entre recargas."""
    await guardar_run_report(sesion_bd, _reporte(fail_logs=[_fail_log(), _fail_log()]))
    await guardar_run_report(
        sesion_bd, _reporte(fail_logs=[_fail_log(motivo="timeout de red")])
    )

    fails = (await sesion_bd.scalars(select(RunFailLog))).all()
    assert len(fails) == 1
    assert fails[0].motivo == "timeout de red"


@requiere_bd
async def test_corridas_de_distintas_fuentes_conviven(sesion_bd):
    """Dos fuentes pueden empezar al mismo tiempo sin pisarse."""
    await guardar_run_report(sesion_bd, _reporte(fuente="autocosmos"))
    await guardar_run_report(sesion_bd, _reporte(fuente="yapo"))

    assert await _contar(sesion_bd, ScrapedRun) == 2


@requiere_bd
async def test_fail_log_malformado_se_omite_sin_perder_el_resto(sesion_bd):
    """Un FAIL LOG sin etapa o motivo se descarta; los válidos igual se guardan."""
    reporte = _reporte(
        fail_logs=[
            _fail_log(),
            {"fuente": "autocosmos", "motivo": "sin etapa"},
            {"fuente": "autocosmos", "etapa": "parseo"},
            "esto no es un dict",
        ]
    )

    run_id = await guardar_run_report(sesion_bd, reporte)

    assert await _contar(sesion_bd, RunFailLog) == 1
    run = await sesion_bd.get(ScrapedRun, run_id)
    assert run.errors == 4, "errors cuenta lo reportado, no lo que se pudo guardar"


@requiere_bd
async def test_etapa_larga_se_trunca_a_la_columna(sesion_bd):
    """`etapa` es String(50): truncar evita que un valor largo aborte la subida."""
    reporte = _reporte(fail_logs=[_fail_log(etapa="x" * 200)])

    await guardar_run_report(sesion_bd, reporte)

    fail = await sesion_bd.scalar(select(RunFailLog))
    assert len(fail.etapa) == 50


@requiere_bd
@pytest.mark.parametrize(
    "reporte, motivo",
    [
        ({"timestamp": _TIMESTAMP}, "sin fuente"),
        ({"fuente": "autocosmos"}, "sin timestamp"),
        ({"fuente": "autocosmos", "timestamp": "no es fecha"}, "timestamp corrupto"),
    ],
)
async def test_reporte_incompleto_no_escribe_nada(sesion_bd, reporte, motivo):
    """Sin clave natural no hay fila que upsertear: se descarta el reporte entero."""
    assert await guardar_run_report(sesion_bd, reporte) is None, motivo
    assert await _contar(sesion_bd, ScrapedRun) == 0


@requiere_bd
async def test_corrida_con_mas_fail_logs_que_un_lote(sesion_bd):
    """Una corrida muy fallida supera el lote de inserción y se guarda igual."""
    from carflip.database.metricas import _LOTE_FAIL_LOGS

    total = _LOTE_FAIL_LOGS + 100
    reporte = _reporte(fail_logs=[_fail_log(id_externo=f"id-{i}") for i in range(total)])

    await guardar_run_report(sesion_bd, reporte)

    assert await _contar(sesion_bd, RunFailLog) == total
