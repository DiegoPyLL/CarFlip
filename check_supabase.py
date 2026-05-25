"""Verifica conexión a Supabase por dos vías: transaction pooler y API REST."""
import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


async def check_pooler():
    import asyncpg

    # Transaction pooler usa puerto 6543; session pooler usa 5432
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace(":5432/", ":6543/")
    conn = await asyncpg.connect(dsn=url, ssl="require")
    version = await conn.fetchval("SELECT version()")
    await conn.close()
    return version


async def check_api():
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/", headers=headers)
        r.raise_for_status()
        return r.status_code, r.text[:120]


async def main():
    print("--- Transaction Pooler (puerto 6543) ---")
    try:
        version = await check_pooler()
        print(f"OK — {version}\n")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}\n")

    print("--- Supabase REST API ---")
    try:
        status, body = await check_api()
        print(f"OK — HTTP {status} — {body}\n")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
