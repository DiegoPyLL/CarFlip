import os
import sys
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Allow importing from src/carflip when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from carflip.database.models import AutocosmosListing, MercadoLibreListing

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_SSL = os.environ.get("USE_SSL", "false").lower() == "true"

_engine = None
_SessionLocal = None


def _get_session_factory() -> async_sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        connect_args: dict = {}
        if USE_SSL:
            connect_args = {"ssl": "require", "prepared_statement_cache_size": 0}
        _engine = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=connect_args)
        _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _SessionLocal

app = FastAPI(title="CarFlip", description="Dashboard de avisos de autos en Chile")

_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)

_SOURCES = {
    "autocosmos": AutocosmosListing,
    "mercadolibre": MercadoLibreListing,
}


def _listing_to_dict(row: Any, source: str) -> dict:
    return {
        "id": row.id,
        "source": source,
        "titulo": row.titulo,
        "url": row.url,
        "precio": float(row.precio) if row.precio is not None else None,
        "moneda": row.moneda,
        "marca": row.marca,
        "modelo": row.modelo,
        "anio": row.anio,
        "km": row.km,
        "ubicacion": row.ubicacion,
        "combustible": row.combustible,
        "url_imagen": row.url_imagen,
        "disponible": row.disponible,
        "precio_anterior": float(row.precio_anterior) if row.precio_anterior is not None else None,
        "delta_pct": row.delta_pct,
        "primera_vez_visto": row.primera_vez_visto.isoformat() if row.primera_vez_visto else None,
        "ultima_vez_visto": row.ultima_vez_visto.isoformat() if row.ultima_vez_visto else None,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/listings")
async def get_listings(
    source: str | None = Query(None),
    marca: str | None = Query(None),
    modelo: str | None = Query(None),
    anio: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    results = []
    async with _get_session_factory()() as session:
        for src_name, model in _SOURCES.items():
            if source and src_name != source:
                continue
            stmt = select(model)
            if marca:
                stmt = stmt.where(func.lower(model.marca) == marca.lower())
            if modelo:
                stmt = stmt.where(func.lower(model.modelo) == modelo.lower())
            if anio:
                stmt = stmt.where(model.anio == anio)
            stmt = stmt.order_by(model.ultima_vez_visto.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            results.extend(_listing_to_dict(r, src_name) for r in rows)

    results.sort(key=lambda x: x["ultima_vez_visto"] or "", reverse=True)
    return results[:limit]


@app.get("/api/sources")
async def get_sources():
    counts = []
    async with _get_session_factory()() as session:
        for src_name, model in _SOURCES.items():
            try:
                total = (await session.execute(select(func.count()).select_from(model))).scalar_one()
            except Exception:
                total = 0
            counts.append({"source": src_name, "total": total})
    return counts
