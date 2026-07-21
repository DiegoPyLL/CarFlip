"""Cliente Groq para categorizar candidatos a deal.

API OpenAI-compatible vía httpx puro (sin SDK). El LLM lee título y
descripción para detectar el estado real del vehículo (motor fundido,
sin papeles, no prende, ...) y clasifica cada aviso del lote.
"""

import asyncio
import json

import httpx
from loguru import logger

from carflip.config import settings
from carflip.deals.tipos import CandidatoDeal, EvaluacionDeal

_URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT_SEGUNDOS = 60.0
_MAX_INTENTOS = 3
_BACKOFF_SEGUNDOS = (2.0, 8.0, 30.0)
_MAX_DESCRIPCION = 1500

CATEGORIAS_VALIDAS = {"oportunidad_clara", "buen_precio", "revisar", "descartar"}

_PROMPT_SISTEMA = """Eres un tasador experto de autos usados en Chile. Recibirás una lista de avisos que \
están significativamente más baratos que su precio de mercado. Tu trabajo es leer \
título y descripción para detectar el estado real del vehículo y clasificar cada aviso.

Categorías:
- "oportunidad_clara": precio muy bajo Y el aviso no menciona daños relevantes.
- "buen_precio": precio atractivo, sin señales de alerta graves, pero margen menor.
- "revisar": precio bajo pero hay ambigüedad (poca descripción, detalles menores, dudas).
- "descartar": el precio bajo se explica por daño grave, falta de papeles, chocado, \
motor fundido, no prende, prenda/embargo, solo repuestos, leasing impago, etc.

Cada aviso trae su "fuente". Si la fuente es "particular", el aviso lo publicó una persona \
directamente en CarFlip y no pasó por la validación de ningún portal: el precio puede ser \
irreal, estar mal tipeado o corresponder a un pie o a una cuota. Ante un precio muy bajo de \
esa fuente sin una explicación clara en la descripción, prefiere "revisar" antes que \
"oportunidad_clara".

Para cada aviso responde:
- puntaje: entero 0-100 (100 = compra inmediata para reventa).
- riesgos: lista corta de riesgos concretos detectados en el texto ("motor fundido", \
"sin papeles", "no prende", "chocado", "km no acreditado"). Lista vacía si no hay.
- resumen: 1 frase en español explicando el veredicto.

Responde SOLO con JSON válido, exactamente con esta estructura:
{"resultados": [{"id": "<id>", "categoria": "...", "puntaje": 0, "riesgos": ["..."], "resumen": "..."}]}
Incluye un resultado por cada aviso recibido, con su mismo id."""

_RECORDATORIO_FORMATO = (
    "Tu respuesta anterior no fue JSON válido con la estructura pedida. Responde SOLO con: "
    '{"resultados": [{"id": "...", "categoria": "...", "puntaje": 0, "riesgos": [], "resumen": "..."}]}'
)


def _mensaje_usuario(candidatos: list[CandidatoDeal]) -> str:
    avisos = []
    for c in candidatos:
        descripcion = (c.descripcion or "")[:_MAX_DESCRIPCION]
        avisos.append(
            {
                "id": c.id_ia,
                "fuente": c.fuente,
                "titulo": c.titulo,
                "anio": c.anio,
                "km": c.km,
                "precio": float(c.precio),
                "precio_mercado": float(c.precio_mercado) if c.precio_mercado is not None else None,
                "pct_vs_mercado": c.pct_vs_mercado,
                "delta_pct": c.delta_pct,
                "descripcion": descripcion,
            }
        )
    return json.dumps({"avisos": avisos}, ensure_ascii=False)


async def _pedir_completion(client: httpx.AsyncClient, mensajes: list[dict]) -> str:
    """POST al endpoint de Groq con retry/backoff ante 429, 5xx y timeouts."""
    body = {
        "model": settings.groq_model,
        "messages": mensajes,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    ultimo_error: Exception | None = None
    for intento in range(_MAX_INTENTOS):
        try:
            respuesta = await client.post(
                _URL_GROQ, json=body, headers=headers, timeout=_TIMEOUT_SEGUNDOS
            )
            if respuesta.status_code == 429 or respuesta.status_code >= 500:
                espera = _BACKOFF_SEGUNDOS[intento]
                retry_after = respuesta.headers.get("retry-after")
                if retry_after is not None:
                    try:
                        espera = max(espera, float(retry_after))
                    except ValueError:
                        pass
                logger.warning(
                    f"[deals/groq] HTTP {respuesta.status_code} — reintento "
                    f"{intento + 1}/{_MAX_INTENTOS} en {espera:.0f}s"
                )
                await asyncio.sleep(espera)
                continue
            respuesta.raise_for_status()
            datos = respuesta.json()
            return datos["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            ultimo_error = exc
            espera = _BACKOFF_SEGUNDOS[intento]
            logger.warning(
                f"[deals/groq] {type(exc).__name__} — reintento "
                f"{intento + 1}/{_MAX_INTENTOS} en {espera:.0f}s"
            )
            await asyncio.sleep(espera)

    raise RuntimeError(f"Groq no respondió tras {_MAX_INTENTOS} intentos: {ultimo_error}")


def _parsear_respuesta(
    contenido: str, candidatos_por_id: dict[str, CandidatoDeal]
) -> list[EvaluacionDeal]:
    """Valida el JSON del LLM. Lanza ValueError si la estructura no sirve."""
    datos = json.loads(contenido)
    resultados = datos.get("resultados")
    if not isinstance(resultados, list):
        raise ValueError("la respuesta no contiene la lista 'resultados'")

    evaluaciones: list[EvaluacionDeal] = []
    for item in resultados:
        if not isinstance(item, dict):
            logger.warning("[deals/groq] Item no es objeto — descartado")
            continue
        candidato = candidatos_por_id.get(str(item.get("id")))
        if candidato is None:
            logger.warning(f"[deals/groq] ID desconocido en respuesta: {item.get('id')!r}")
            continue
        categoria = item.get("categoria")
        if categoria not in CATEGORIAS_VALIDAS:
            logger.warning(
                f"[deals/groq] Categoría inválida {categoria!r} para {candidato.id_ia} — descartado"
            )
            continue
        try:
            puntaje = int(item.get("puntaje"))
        except (TypeError, ValueError):
            logger.warning(f"[deals/groq] Puntaje inválido para {candidato.id_ia} — descartado")
            continue
        puntaje = max(0, min(100, puntaje))
        riesgos_crudos = item.get("riesgos") or []
        riesgos = [str(r) for r in riesgos_crudos if isinstance(r, (str, int, float))]
        resumen = str(item.get("resumen") or "")

        evaluaciones.append(
            EvaluacionDeal(
                fuente=candidato.fuente,
                id_externo=candidato.id_externo,
                categoria=categoria,
                puntaje=puntaje,
                riesgos=riesgos,
                resumen=resumen,
            )
        )
    return evaluaciones


async def categorizar_lote(
    client: httpx.AsyncClient, candidatos: list[CandidatoDeal]
) -> list[EvaluacionDeal]:
    """Categoriza un lote de candidatos con Groq.

    Ante JSON malformado reintenta una vez recordando el formato; si vuelve a
    fallar retorna lista vacía (el lote se reintentará en la próxima corrida).
    """
    if not candidatos:
        return []

    candidatos_por_id = {c.id_ia: c for c in candidatos}
    mensajes = [
        {"role": "system", "content": _PROMPT_SISTEMA},
        {"role": "user", "content": _mensaje_usuario(candidatos)},
    ]

    contenido = await _pedir_completion(client, mensajes)
    try:
        return _parsear_respuesta(contenido, candidatos_por_id)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"[deals/groq] JSON malformado ({exc}) — reintentando lote una vez")

    mensajes_retry = mensajes + [
        {"role": "assistant", "content": contenido},
        {"role": "user", "content": _RECORDATORIO_FORMATO},
    ]
    contenido = await _pedir_completion(client, mensajes_retry)
    try:
        return _parsear_respuesta(contenido, candidatos_por_id)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(
            f"[deals/groq] Lote de {len(candidatos)} candidatos descartado — "
            f"JSON inválido tras reintento ({exc})"
        )
        return []
