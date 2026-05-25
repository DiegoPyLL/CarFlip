"""Verifica conexión a Supabase por tres vías, en orden de lo más simple a lo más real."""
import asyncio
import os

import httpx
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


async def check_api():
    """REST API — lo más básico, solo verifica URL y SERVICE_KEY."""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/", headers=headers)
        r.raise_for_status()
        return r.status_code, r.text[:120]


async def check_sqlalchemy_scraper():
    """SQLAlchemy — idéntico a lo que usa session.py en los scrapers."""
    import sys
    sys.path.insert(0, "src")
    from carflip.config import settings
    from carflip.database.session import engine

    async with engine.connect() as conn:
        row = await conn.execute(text("SELECT current_user, current_database(), version()"))
        return row.fetchone()


async def check_sqlalchemy_ssl():
    """SQLAlchemy con SSL forzado — para comparar si el problema es SSL."""
    connect_args = {"ssl": "require", "statement_cache_size": 0}
    e = create_async_engine(DATABASE_URL, connect_args=connect_args)
    async with e.connect() as conn:
        row = await conn.execute(text("SELECT current_user, current_database()"))
        return row.fetchone()


async def main():
    print("=" * 60)
    print("1. Supabase REST API (verifica URL + SERVICE_KEY)")
    print("=" * 60)
    try:
        status, body = await check_api()
        print(f"OK — HTTP {status}\n")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}\n")

    print("=" * 60)
    print("2. SQLAlchemy — igual que los scrapers (usa settings)")
    print("=" * 60)
    try:
        row = await check_sqlalchemy_scraper()
        print(f"OK — usuario={row[0]}, db={row[1]}\n")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}\n")

    print("=" * 60)
    print("3. SQLAlchemy con SSL forzado (para comparar)")
    print("=" * 60)
    try:
        row = await check_sqlalchemy_ssl()
        print(f"OK — usuario={row[0]}, db={row[1]}\n")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
