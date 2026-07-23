"""Fixtures compartidos para la suite de tests de CarFlip."""

import os
from unittest.mock import AsyncMock, MagicMock

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
                "TRUNCATE autocosmos_listings, yapo_listings, autosusados_listings, "
                "checkeados_listings, particulares_listings, perfiles, "
                "market_snapshots, scrape_runs, run_fail_logs RESTART IDENTITY CASCADE"
            )
        )

    async with async_sessionmaker(engine, expire_on_commit=False)() as sesion:
        yield sesion

    await engine.dispose()


@pytest.fixture(autouse=True)
def delays_cero(monkeypatch):
    """Anula las esperas aleatorias entre requests para que los tests no se ralenticen."""
    from carflip.config import settings

    monkeypatch.setattr(settings, "min_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "max_delay_seconds", 0.0)


@pytest.fixture
def html_listado_autocosmos() -> str:
    """HTML de listado de Autocosmos con 2 avisos válidos y 1 inválido (precio bajo el mínimo)."""
    return """
    <html><body>
      <a href="/auto/usado/toyota/corolla/sedan/111">
        <img src="https://img.autocosmos.cl/1.webp" alt="Toyota Corolla 2020"/>
        Santiago | $ 8.500.000 | 85.000 km | 2020
      </a>
      <a href="/auto/usado/ford/fiesta/hatchback/222">
        <img src="https://img.autocosmos.cl/2.webp" alt="Ford Fiesta 2019"/>
        Valparaiso | $ 6.000.000 | 100.000 km | 2019
      </a>
      <a href="/auto/usado/kia/rio/sedan/333">
        <img src="https://img.autocosmos.cl/3.webp" alt="Kia Rio 2018"/>
        Concepcion | $ 100.000 | 50.000 km | 2018
      </a>
      <a href="/seccion/no-aviso">no es aviso</a>
    </body></html>
    """


def _crear_card_yapo(href: str, fecha: str = "2024-03-15") -> AsyncMock:
    """Crea un mock de card de Yapo con los selectores que usa el scraper."""
    link = AsyncMock()
    link.get_attribute = AsyncMock(return_value=href)

    nodo_precio = AsyncMock()
    nodo_precio.inner_text = AsyncMock(return_value="$ 8.500.000")
    nodo_region = AsyncMock()
    nodo_region.inner_text = AsyncMock(return_value="Santiago")
    nodo_time = AsyncMock()
    nodo_time.get_attribute = AsyncMock(return_value=fecha)

    def query_selector(sel: str):
        if sel.startswith("a[href"):
            return link
        if "price" in sel:
            return nodo_precio
        if "location" in sel:
            return nodo_region
        if "time" in sel:
            return nodo_time
        return None

    card = AsyncMock()
    card.query_selector = AsyncMock(side_effect=query_selector)
    return card


@pytest.fixture
def mock_playwright():
    """Mockea async_playwright con 2 cards en el listado y atributos fijos en el detalle.

    Retorna (mock_async_playwright, page) — el test parchea
    carflip.scrapers.Yapo.yapoCloud.async_playwright con el primero.
    """
    cards = [
        _crear_card_yapo("/autos-usados/region_metropolitana/toyota/corolla/2020/1234560"),
        _crear_card_yapo("/autos-usados/region_metropolitana/toyota/corolla/2020/1234561"),
    ]

    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.route = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=cards)
    page.evaluate = AsyncMock(return_value={
        "Marca": "Toyota",
        "Modelo": "Corolla",
        "Año": "2020",
        "Kilómetros": "85.000",
        "Combustible": "Bencina",
        "imagen_url": "",
    })
    page.close = AsyncMock()

    ctx = AsyncMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.close = AsyncMock()

    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=ctx)
    browser.close = AsyncMock()

    p = MagicMock()
    p.chromium = MagicMock()
    p.chromium.launch = AsyncMock(return_value=browser)

    pw_cm = MagicMock()
    pw_cm.__aenter__ = AsyncMock(return_value=p)
    pw_cm.__aexit__ = AsyncMock(return_value=None)

    mock_async_playwright = MagicMock(return_value=pw_cm)
    return mock_async_playwright, page
