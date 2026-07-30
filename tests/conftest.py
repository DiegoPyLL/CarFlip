"""Fixtures compartidos para la suite de tests de CarFlip."""

import os

import pytest
import pytest_asyncio

# Los tests que escriben en Postgres corren contra una BD desechable, nunca
# contra la de producción: se activan exportando CARFLIP_TEST_DATABASE_URL.
URL_BD_TEST = os.environ.get("CARFLIP_TEST_DATABASE_URL")

skip_sin_bd_test = pytest.mark.skipif(
    not URL_BD_TEST,
    reason="requiere CARFLIP_TEST_DATABASE_URL apuntando a una BD de test",
)


def requiere_bd(test):
    """Marca un test como de integración y lo salta si no hay BD de test."""
    return pytest.mark.integration(skip_sin_bd_test(test))


def pytest_addoption(parser):
    """`--supabase` habilita los tests que escriben en el Supabase real.

    Va aquí porque pytest solo admite `pytest_addoption` en el conftest raíz.
    Existe además de la variable de entorno porque `VAR=1 pytest ...` no asigna
    nada en PowerShell, que es el shell del proyecto en Windows: sin esta opción
    el opt-in se pierde en silencio y la suite se salta entera.
    """
    parser.addoption(
        "--supabase",
        action="store_true",
        default=False,
        help="ejecuta los tests de integración que escriben en el Supabase real",
    )


@pytest_asyncio.fixture
async def sesion_bd():
    """Sesión contra la BD de test con el esquema creado y las tablas vacías.

    Cada test parte de cero: se truncan las tablas que tocan los tests de
    escritura en vez de recrear el esquema, que es un orden de magnitud más
    lento y no aporta aislamiento adicional dentro de una BD desechable.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from carflip.database.models import Base

    engine = create_async_engine(URL_BD_TEST)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "TRUNCATE particulares_listings, perfiles, market_snapshots, deals "
                "RESTART IDENTITY CASCADE"
            )
        )

    async with async_sessionmaker(engine, expire_on_commit=False)() as sesion:
        yield sesion

    await engine.dispose()
