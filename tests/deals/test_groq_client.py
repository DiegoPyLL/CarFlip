"""Tests unitarios del cliente Groq — HTTP mockeado con respx."""

import json

import httpx
import pytest
import respx

from carflip.deals import groq_client
from carflip.deals.groq_client import _URL_GROQ, categorizar_lote


def _respuesta_llm(contenido: str) -> dict:
    """Envuelve el contenido en la estructura de respuesta OpenAI-compatible."""
    return {"choices": [{"message": {"content": contenido}}]}


def _resultado(id_: str, categoria: str = "buen_precio", puntaje: int = 70, **extra) -> dict:
    return {"id": id_, "categoria": categoria, "puntaje": puntaje,
            "riesgos": extra.get("riesgos", []), "resumen": extra.get("resumen", "ok")}


@pytest.fixture(autouse=True)
def sin_esperas(mocker):
    """Evita que los backoffs duerman de verdad durante los tests."""
    mocker.patch("carflip.deals.groq_client.asyncio.sleep", new=mocker.AsyncMock())


@respx.mock
async def test_respuesta_valida(hacer_candidato):
    candidato = hacer_candidato()
    contenido = json.dumps(
        {"resultados": [_resultado(candidato.id_ia, "oportunidad_clara", 92,
                                   riesgos=["km no acreditado"], resumen="Muy bajo el mercado")]}
    )
    respx.post(_URL_GROQ).mock(return_value=httpx.Response(200, json=_respuesta_llm(contenido)))

    async with httpx.AsyncClient() as client:
        evaluaciones = await categorizar_lote(client, [candidato])

    assert len(evaluaciones) == 1
    ev = evaluaciones[0]
    assert ev.fuente == "yapo"
    assert ev.id_externo == "abc123"
    assert ev.categoria == "oportunidad_clara"
    assert ev.puntaje == 92
    assert ev.riesgos == ["km no acreditado"]
    assert ev.resumen == "Muy bajo el mercado"


@respx.mock
async def test_json_malformado_reintenta_y_descarta(hacer_candidato):
    candidato = hacer_candidato()
    ruta = respx.post(_URL_GROQ).mock(
        return_value=httpx.Response(200, json=_respuesta_llm("esto no es json"))
    )

    async with httpx.AsyncClient() as client:
        evaluaciones = await categorizar_lote(client, [candidato])

    assert evaluaciones == []
    assert ruta.call_count == 2  # intento original + reintento con recordatorio


@respx.mock
async def test_json_malformado_recupera_en_reintento(hacer_candidato):
    candidato = hacer_candidato()
    contenido_ok = json.dumps({"resultados": [_resultado(candidato.id_ia)]})
    ruta = respx.post(_URL_GROQ).mock(
        side_effect=[
            httpx.Response(200, json=_respuesta_llm("{sin cerrar")),
            httpx.Response(200, json=_respuesta_llm(contenido_ok)),
        ]
    )

    async with httpx.AsyncClient() as client:
        evaluaciones = await categorizar_lote(client, [candidato])

    assert len(evaluaciones) == 1
    assert ruta.call_count == 2


@respx.mock
async def test_categoria_invalida_descarta_item(hacer_candidato):
    candidato = hacer_candidato()
    contenido = json.dumps({"resultados": [_resultado(candidato.id_ia, categoria="ganga")]})
    respx.post(_URL_GROQ).mock(return_value=httpx.Response(200, json=_respuesta_llm(contenido)))

    async with httpx.AsyncClient() as client:
        evaluaciones = await categorizar_lote(client, [candidato])

    assert evaluaciones == []


@respx.mock
async def test_puntaje_fuera_de_rango_se_clampa(hacer_candidato):
    c1 = hacer_candidato(id_externo="a1")
    c2 = hacer_candidato(id_externo="a2")
    contenido = json.dumps(
        {"resultados": [_resultado(c1.id_ia, puntaje=150), _resultado(c2.id_ia, puntaje=-10)]}
    )
    respx.post(_URL_GROQ).mock(return_value=httpx.Response(200, json=_respuesta_llm(contenido)))

    async with httpx.AsyncClient() as client:
        evaluaciones = await categorizar_lote(client, [c1, c2])

    puntajes = {ev.id_externo: ev.puntaje for ev in evaluaciones}
    assert puntajes == {"a1": 100, "a2": 0}


@respx.mock
async def test_id_desconocido_se_ignora(hacer_candidato):
    candidato = hacer_candidato()
    contenido = json.dumps(
        {"resultados": [_resultado(candidato.id_ia), _resultado("yapo-fantasma")]}
    )
    respx.post(_URL_GROQ).mock(return_value=httpx.Response(200, json=_respuesta_llm(contenido)))

    async with httpx.AsyncClient() as client:
        evaluaciones = await categorizar_lote(client, [candidato])

    assert len(evaluaciones) == 1
    assert evaluaciones[0].id_externo == "abc123"


@respx.mock
async def test_429_reintenta_con_backoff(hacer_candidato):
    candidato = hacer_candidato()
    contenido = json.dumps({"resultados": [_resultado(candidato.id_ia)]})
    ruta = respx.post(_URL_GROQ).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "1"}),
            httpx.Response(200, json=_respuesta_llm(contenido)),
        ]
    )

    async with httpx.AsyncClient() as client:
        evaluaciones = await categorizar_lote(client, [candidato])

    assert len(evaluaciones) == 1
    assert ruta.call_count == 2


@respx.mock
async def test_errores_persistentes_lanzan(hacer_candidato):
    candidato = hacer_candidato()
    respx.post(_URL_GROQ).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError):
            await categorizar_lote(client, [candidato])


async def test_lote_vacio_no_llama_api():
    async with httpx.AsyncClient() as client:
        assert await categorizar_lote(client, []) == []


def test_descripcion_se_trunca(hacer_candidato):
    candidato = hacer_candidato(descripcion="x" * 5000)
    mensaje = json.loads(groq_client._mensaje_usuario([candidato]))
    assert len(mensaje["avisos"][0]["descripcion"]) == groq_client._MAX_DESCRIPCION
