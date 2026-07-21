"""Orquestador del pipeline de deals.

Flujo: candidatos.sql → filtro anti-re-tokenización → Groq por lotes →
upsert en tabla deals → desactivación de deals que dejaron de ser candidatos.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx
from loguru import logger
from sqlalchemy import func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.config import settings
from carflip.database.models import Deal
from carflip.deals.groq_client import categorizar_lote
from carflip.deals.tipos import CandidatoDeal, EvaluacionDeal

_SQL_CANDIDATOS = (Path(__file__).parent / "candidatos.sql").read_text(encoding="utf-8")
_PAUSA_ENTRE_LOTES = 2.5  # segundos — free tier Groq ~30 req/min


async def _obtener_candidatos(session: AsyncSession) -> list[CandidatoDeal]:
    resultado = await session.execute(
        text(_SQL_CANDIDATOS),
        {
            "umbral_pct": settings.deal_threshold_pct,
            "min_comparables": settings.deal_min_comparables,
            "min_comparables_particular": settings.deal_min_comparables_particular,
            "max_candidatos": settings.deal_max_candidatos,
        },
    )
    candidatos = []
    for fila in resultado.mappings():
        candidatos.append(
            CandidatoDeal(
                fuente=fila["fuente"],
                id_externo=fila["id_externo"],
                url=fila["url"],
                titulo=fila["titulo"],
                precio=fila["precio"],
                moneda=fila["moneda"] or "CLP",
                marca=fila["marca"],
                modelo=fila["modelo"],
                anio=fila["anio"],
                km=fila["km"],
                ubicacion=fila["ubicacion"],
                descripcion=fila["descripcion"],
                url_imagen=fila["url_imagen"],
                delta_pct=float(fila["delta_pct"]) if fila["delta_pct"] is not None else None,
                precio_mercado=fila["precio_mercado"],
                comparables=fila["comparables"],
                pct_vs_mercado=(
                    float(fila["pct_vs_mercado"]) if fila["pct_vs_mercado"] is not None else None
                ),
            )
        )
    return candidatos


async def _obtener_previos(
    session: AsyncSession, candidatos: list[CandidatoDeal]
) -> dict[tuple[str, str], tuple[Decimal | None, datetime | None]]:
    """Estado previo de categorización para decidir si re-gastar tokens."""
    pares = [(c.fuente, c.id_externo) for c in candidatos]
    resultado = await session.execute(
        select(Deal.fuente, Deal.id_externo, Deal.precio_al_categorizar, Deal.categorizado_en).where(
            tuple_(Deal.fuente, Deal.id_externo).in_(pares)
        )
    )
    return {(f, i): (precio, fecha) for f, i, precio, fecha in resultado.all()}


def _necesita_ia(
    candidato: CandidatoDeal,
    previos: dict[tuple[str, str], tuple[Decimal | None, datetime | None]],
) -> bool:
    """True si el candidato debe ir al LLM: nuevo, cambió de precio o su evaluación venció."""
    previo = previos.get((candidato.fuente, candidato.id_externo))
    if previo is None:
        return True
    precio_al_categorizar, categorizado_en = previo
    if precio_al_categorizar is None or categorizado_en is None:
        return True
    if precio_al_categorizar != candidato.precio:
        return True
    limite = datetime.now(timezone.utc) - timedelta(days=settings.deal_recategorizar_dias)
    return categorizado_en < limite


def _lotes(items: list[CandidatoDeal], tamano: int) -> list[list[CandidatoDeal]]:
    return [items[i : i + tamano] for i in range(0, len(items), tamano)]


def _fila_deal(candidato: CandidatoDeal) -> dict:
    return {
        "fuente": candidato.fuente,
        "id_externo": candidato.id_externo,
        "url": candidato.url,
        "titulo": candidato.titulo,
        "marca": candidato.marca,
        "modelo": candidato.modelo,
        "anio": candidato.anio,
        "km": candidato.km,
        "ubicacion": candidato.ubicacion,
        "precio": candidato.precio,
        "moneda": candidato.moneda,
        "url_imagen": candidato.url_imagen,
        "precio_mercado": candidato.precio_mercado,
        "pct_vs_mercado": candidato.pct_vs_mercado,
        "delta_pct": candidato.delta_pct,
        "comparables": candidato.comparables,
        "activo": True,
    }


async def _upsert_deals(
    session: AsyncSession,
    candidatos: list[CandidatoDeal],
    evaluaciones: dict[tuple[str, str], EvaluacionDeal],
) -> int:
    """Upsert de candidatos en la tabla deals.

    Los evaluados en esta corrida actualizan también los campos IA; el resto
    solo refresca snapshot + contexto de mercado sin pisar la evaluación previa.
    """
    tabla = Deal.__table__

    def set_comun(stmt) -> dict:
        return {
            "url": stmt.excluded.url,
            "titulo": stmt.excluded.titulo,
            "marca": stmt.excluded.marca,
            "modelo": stmt.excluded.modelo,
            "anio": stmt.excluded.anio,
            "km": stmt.excluded.km,
            "ubicacion": stmt.excluded.ubicacion,
            "precio": stmt.excluded.precio,
            "moneda": stmt.excluded.moneda,
            "url_imagen": stmt.excluded.url_imagen,
            "precio_mercado": stmt.excluded.precio_mercado,
            "pct_vs_mercado": stmt.excluded.pct_vs_mercado,
            "delta_pct": stmt.excluded.delta_pct,
            "comparables": stmt.excluded.comparables,
            "activo": True,
            "actualizado_en": func.now(),
        }

    total = 0

    sin_ia = [
        _fila_deal(c) for c in candidatos if (c.fuente, c.id_externo) not in evaluaciones
    ]
    if sin_ia:
        stmt = insert(tabla).values(sin_ia)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_deals_fuente_id_externo", set_=set_comun(stmt)
        )
        resultado = await session.execute(stmt)
        total += resultado.rowcount

    con_ia = []
    for c in candidatos:
        ev = evaluaciones.get((c.fuente, c.id_externo))
        if ev is None:
            continue
        fila = _fila_deal(c)
        fila.update(
            {
                "categoria": ev.categoria,
                "puntaje": ev.puntaje,
                "riesgos": ev.riesgos,
                "resumen": ev.resumen,
                "modelo_ia": settings.groq_model,
                "categorizado_en": datetime.now(timezone.utc),
                "precio_al_categorizar": c.precio,
            }
        )
        con_ia.append(fila)
    if con_ia:
        stmt = insert(tabla).values(con_ia)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_deals_fuente_id_externo",
            set_={
                **set_comun(stmt),
                "categoria": stmt.excluded.categoria,
                "puntaje": stmt.excluded.puntaje,
                "riesgos": stmt.excluded.riesgos,
                "resumen": stmt.excluded.resumen,
                "modelo_ia": stmt.excluded.modelo_ia,
                "categorizado_en": func.now(),
                "precio_al_categorizar": stmt.excluded.precio_al_categorizar,
            },
        )
        resultado = await session.execute(stmt)
        total += resultado.rowcount

    return total


async def _desactivar_obsoletos(
    session: AsyncSession, candidatos: list[CandidatoDeal]
) -> int:
    """Desactiva deals activos que ya no aparecen entre los candidatos."""
    stmt = update(Deal).where(Deal.activo.is_(True)).values(activo=False, actualizado_en=func.now())
    if candidatos:
        pares = [(c.fuente, c.id_externo) for c in candidatos]
        stmt = stmt.where(tuple_(Deal.fuente, Deal.id_externo).not_in(pares))
    resultado = await session.execute(stmt)
    return resultado.rowcount


async def detectar_deals(session: AsyncSession) -> int:
    """Pipeline completo de deals. Retorna el número de deals activos."""
    candidatos = await _obtener_candidatos(session)
    logger.info(f"[deals] {len(candidatos)} candidatos seleccionados por candidatos.sql")

    evaluaciones: dict[tuple[str, str], EvaluacionDeal] = {}
    if candidatos:
        previos = await _obtener_previos(session, candidatos)
        a_evaluar = [c for c in candidatos if _necesita_ia(c, previos)]
        ya_vigentes = len(candidatos) - len(a_evaluar)
        logger.info(
            f"[deals] {len(a_evaluar)} candidatos a evaluar con IA, "
            f"{ya_vigentes} con categorización vigente"
        )

        if a_evaluar and not settings.groq_api_key:
            logger.warning("[deals] GROQ_API_KEY no configurada — se upsertean sin categorizar")
        elif a_evaluar:
            lotes = _lotes(a_evaluar, settings.deal_lote_ia)
            async with httpx.AsyncClient() as client:
                for i, lote in enumerate(lotes, start=1):
                    try:
                        resultados = await categorizar_lote(client, lote)
                    except Exception:
                        logger.exception(f"[deals] Lote {i}/{len(lotes)} falló — se omite")
                        resultados = []
                    for ev in resultados:
                        evaluaciones[(ev.fuente, ev.id_externo)] = ev
                    if i < len(lotes):
                        await asyncio.sleep(_PAUSA_ENTRE_LOTES)
            logger.info(f"[deals] {len(evaluaciones)} candidatos categorizados por Groq")

    upserted = await _upsert_deals(session, candidatos, evaluaciones)
    desactivados = await _desactivar_obsoletos(session, candidatos)
    await session.commit()

    activos = await session.scalar(
        select(func.count()).select_from(Deal).where(Deal.activo.is_(True))
    )
    logger.info(
        f"[deals] Corrida terminada — {upserted} upserted, {desactivados} desactivados, "
        f"{activos} deals activos"
    )
    return int(activos or 0)
