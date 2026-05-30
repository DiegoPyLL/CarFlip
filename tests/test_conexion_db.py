"""Tests de integración: verifica conectividad a la base de datos por tres vías.

Requieren variables de entorno reales. Se saltan automáticamente si no están disponibles.
Ejecutar con: pytest -m integration -v tests/test_conexion_db.py
"""

import os

import pytest
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.integration

_tiene_db_url = bool(os.getenv("DATABASE_URL"))
_tiene_supabase = bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_SERVICE_KEY"))

skip_sin_supabase = pytest.mark.skipif(
    not _tiene_supabase,
    reason="SUPABASE_URL y SUPABASE_SERVICE_KEY no configuradas",
)
skip_sin_db = pytest.mark.skipif(
    not _tiene_db_url,
    reason="DATABASE_URL no configurada",
)


@skip_sin_supabase
@pytest.mark.asyncio
async def test_supabase_rest_api():
    """REST API responde 200 con URL y SERVICE_KEY válidas."""
    import httpx

    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{supabase_url}/rest/v1/", headers=headers)
    assert r.status_code == 200, f"Esperaba 200, obtuvo {r.status_code}: {r.text[:200]}"


@skip_sin_db
@pytest.mark.asyncio
async def test_sqlalchemy_conexion():
    """SQLAlchemy conecta correctamente usando la session del proyecto."""
    from sqlalchemy import text

    from carflip.database.session import engine

    async with engine.connect() as conn:
        row = await conn.execute(
            text("SELECT current_user, current_database(), version()")
        )
        resultado = row.fetchone()

    assert resultado is not None
    assert resultado[0], "current_user vacío"
    assert resultado[1], "current_database() vacío"


@skip_sin_db
@pytest.mark.asyncio
async def test_sqlalchemy_ssl_forzado():
    """SQLAlchemy conecta con SSL requerido explícitamente."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    database_url = os.getenv("DATABASE_URL")
    connect_args = {"ssl": "require", "statement_cache_size": 0}
    engine = create_async_engine(database_url, connect_args=connect_args)
    try:
        async with engine.connect() as conn:
            row = await conn.execute(text("SELECT current_user, current_database()"))
            resultado = row.fetchone()
    finally:
        await engine.dispose()

    assert resultado is not None
    assert resultado[0], "current_user vacío"
    assert resultado[1], "current_database() vacío"
