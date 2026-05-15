# GEMINI.md — CarFlip Pipeline de Datos de Avisos de Autos

> Documento de referencia del proyecto. Estado actual, arquitectura objetivo, decisiones tomadas e inconsistencias pendientes.

---

## Qué es CarFlip

Plataforma que agrega avisos de autos en venta desde 5 portales chilenos, normaliza los datos, los persiste en PostgreSQL y detecta oportunidades de compra (deals) mediante análisis de historial de precios.

---

## Decisiones de diseño

Estas decisiones se tomaron el 2026-05-11 y rigen todo el desarrollo futuro:

| Tema | Decisión |
|------|----------|
| Fuentes | Solo 5: MercadoLibre (API), Autocosmos, Autosusados, Checkeados, Económicos |
| Fuentes eliminadas | Yapo, ChileAutos, Facebook — eliminar código, imports y tests |
| Naming del código | Todo en español: `AvisoAuto`, `ScraperBase`, `ejecutar()`, `espera_aleatoria()` |
| Arquitectura | Híbrido: CSV raw como backup en `data/raw/` + upsert directo a PostgreSQL |
| Base de datos | PostgreSQL async (SQLAlchemy 2.0 + asyncpg + Alembic) |
| Scraping HTTP | httpx + BeautifulSoup4 + lxml para los 5 sitios |
| Scraping headless | Playwright + stealth se mantiene en dependencias como reserva |
| Credenciales | Solo `.env` — eliminar keyring, Fernet, AWS Secrets Manager, `credentials.py` |
| CLI | Mantener click: `carflip run`, `carflip start`, `carflip market` |
| Logging | loguru (no `print()` nunca) |
| Tests | pytest + pytest-asyncio + pytest-mock |
| Gestor de paquetes | uv |

---

## Estado actual del código vs objetivo

### Inconsistencias críticas a resolver

Estas son las que probablemente rompen en runtime:

**1. Nombre del paquete**
- `pyproject.toml` dice `carflipper` y apunta a `src/carflipper/`
- El código real vive en `src/carflip/` y los imports son `from carflip.config import settings`
- El README usa `carflip` como comando CLI
- **Resolver**: Alinear `pyproject.toml` a `carflip` (que es lo real)

**2. Nombres en `price_tracker.py` no coinciden con `base.py`**
- `price_tracker.py` importa `CarListing` y `ScrapeResult` (no existen)
- `base.py` define `AvisoAuto` y `ResultadoScraping`
- **Resolver**: Actualizar `price_tracker.py` a los nombres en español

**3. Nombres de métodos en `runner.py` no coinciden con `base.py`**
- `runner.py` llama `scraper.run(session)` (no existe)
- `base.py` define `ejecutar(sesion)`
- **Resolver**: Actualizar `runner.py` a `scraper.ejecutar(session)`

**4. Columnas de `models.py` en inglés vs dataclass en español**
- `Listing` tiene `brand`, `model`, `year`, `source`, `external_id`
- `AvisoAuto` tiene `marca`, `modelo`, `anio`, `fuente`, `id_externo`
- **Decidir**: El ORM puede quedarse en inglés (son nombres de columnas SQL), pero el mapeo en `price_tracker.py` debe traducir correctamente entre ambos

**5. `CLAUDE.md` desactualizado**
- Referencia rutas `src/carflipper/` (no existe)
- Documenta `BaseScraper`, `CarListing`, `run()`, `random_delay()` (nombres inglés que no son los reales)
- Describe keyring y Fernet como mecanismos de credenciales (se eliminan)
- **Resolver**: Reescribir después de aplicar todos los cambios

**6. Scrapers obsoletos siguen en `runner.py`**
- Importa `ChileautosScraper`, `YapoScraper`, `FacebookScraper`
- **Resolver**: Eliminar imports y reemplazar con los 5 scrapers nuevos

**7. Tabla `session_cookies` ya no se necesita**
- Existía para cookies cifradas de Facebook
- **Resolver**: Crear migración Alembic para eliminarla

**8. Comando `credentials` del CLI ya no se necesita**
- Sin keyring ni login a sitios, el subcomando sobra
- **Resolver**: Eliminar de `__main__.py`

---

## Fuentes de datos

### 1. MercadoLibre — `api.mercadolibre.com`

| Propiedad | Valor |
|-----------|-------|
| Tipo | API REST oficial |
| Formato | JSON estructurado |
| Auth | Token via `MERCADOLIBRE_APP_ID` + `MERCADOLIBRE_CLIENT_SECRET` en `.env` |
| Herramientas | `httpx` (sin BS4 necesario) |
| Volumen | Alto |
| Anti-bot | Rate limiting de la API |

Es el único sitio donde no se escribe un scraper HTML sino un cliente HTTP contra endpoints JSON. Los campos ya vienen normalizados.

### 2. Autocosmos — `autocosmos.cl`

| Propiedad | Valor |
|-----------|-------|
| Tipo | HTML server-side (PHP) |
| Formato | DOM estable y predecible |
| Auth | Ninguna |
| Herramientas | `httpx` + `BeautifulSoup4` |
| Volumen | Medio |
| Anti-bot | Sin Cloudflare, sin JS necesario |

### 3. Autosusados — `autosusados.cl`

| Propiedad | Valor |
|-----------|-------|
| Tipo | HTML server-side |
| Formato | Estructura limpia |
| Auth | Ninguna |
| Herramientas | `httpx` + `BeautifulSoup4` |
| Volumen | Medio-Bajo |
| Anti-bot | Sin protecciones apreciables |

### 4. Checkeados — `checkeados.cl`

| Propiedad | Valor |
|-----------|-------|
| Tipo | HTML server-side |
| Formato | DOM sencillo |
| Auth | Ninguna |
| Herramientas | `httpx` + `BeautifulSoup4` |
| Volumen | Bajo (automotora única) |
| Anti-bot | Protección nula |

### 5. Económicos — `economicos.cl`

| Propiedad | Valor |
|-----------|-------|
| Tipo | HTML server-side (grupo El Mercurio) |
| Formato | DOM estándar |
| Auth | Ninguna |
| Herramientas | `httpx` + `BeautifulSoup4` |
| Volumen | Medio |
| Anti-bot | Sin Cloudflare |

Particularidad: incluye particulares además de automotoras, lo que aporta variedad al dataset.

---

## Arquitectura

### Flujo de datos

```
CLI (carflip run / carflip start)
    │
    ▼
runner.run_all_scrapers()
    │
    └─ Para cada scraper (ScraperBase.ejecutar(sesion)):
          ├─ scraper.scrape()              ← lógica específica del sitio
          │     ├─ HTTP request (httpx)
          │     ├─ Parse (BS4 o JSON)
          │     ├─ espera_aleatoria()      ← rate limiting entre requests
          │     └─ return list[AvisoAuto]
          │
          └─ uploader.upsert_avisos(sesion, avisos, model_class)
                ├─ INSERT INTO {fuente}_listings ... ON CONFLICT (id_externo) DO UPDATE
                └─ Si cambió precio → actualiza precio_anterior y delta_pct inline
```

### Patrón de scrapers

Todos heredan de `ScraperBase` en `src/carflip/scrapers/base.py`. El único método a implementar es `scrape() -> list[AvisoAuto]`. El método `ejecutar()` de la clase base gestiona logging, timing y manejo de errores.

Siempre llamar `await self.espera_aleatoria()` entre requests HTTP.

### Dataclass normalizado

```python
@dataclass
class AvisoAuto:
    fuente: str
    id_externo: str
    url: str
    titulo: str
    precio: Decimal | None = None
    moneda: str = "CLP"
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    km: int | None = None
    ubicacion: str | None = None
    combustible: str | None = None
    descripcion: str | None = None
    url_imagen: str | None = None
    disponible: bool | None = None
    fecha_publicacion: str | None = None
```

Todo scraper mapea sus datos a `AvisoAuto`, sin importar si la fuente es HTML o JSON.

---

## Estructura de directorios (objetivo)

```
carflip/
├── pyproject.toml
├── alembic.ini
├── .env                          # credenciales y config (no va a git)
├── .env.example
├── .gitignore
├── README.md
├── GEMINI.md                     # ← este archivo
├── CLAUDE.md                     # guía para Claude Code (por reescribir)
├── CHANGELOG.md
│
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_eliminar_session_cookies.py    # pendiente
│
├── data/
│   └── raw/                      # CSV backup por fuente y fecha
│       └── .gitkeep
│
├── logs/                         # rotación con loguru
│
├── src/
│   └── carflip/
│       ├── __init__.py
│       ├── __main__.py           # CLI click (carflip run/start/market)
│       ├── config.py             # pydantic-settings, lee .env
│       │
│       ├── scrapers/
│       │   ├── __init__.py
│       │   ├── base.py           # ScraperBase + AvisoAuto + ResultadoScraping
│       │   ├── mercadolibre.py   # Cliente API REST (httpx + JSON)
│       │   ├── autocosmos.py     # httpx + BS4
│       │   ├── autosusados.py    # httpx + BS4
│       │   ├── checkeados.py     # httpx + BS4       ← NUEVO
│       │   └── economicos.py     # httpx + BS4       ← NUEVO
│       │
│       ├── database/
│       │   ├── __init__.py
│       │   ├── models.py         # Listing, PriceHistory, ScrapedRun
│       │   ├── session.py        # AsyncSessionLocal
│       │   └── price_tracker.py  # upsert + delta precios + deals
│       │
│       └── scheduler/
│           └── runner.py         # ejecutar_todos + APScheduler
│
└── tests/
    ├── __init__.py
    ├── test_scrapers.py
    ├── test_price_tracker.py
    └── test_models.py
```

**Archivos a ELIMINAR**:
- `src/carflip/scrapers/yapo.py`
- `src/carflip/scrapers/chileautos.py`
- `src/carflip/scrapers/facebook.py`
- `src/carflip/credentials.py`

---

## Stack tecnológico

| Componente | Tecnología | Versión | Notas |
|-----------|-----------|---------|-------|
| Lenguaje | Python | 3.12+ | gestionado con uv |
| HTTP | httpx | ≥0.27 | async, para todos los scrapers |
| HTML Parser | BeautifulSoup4 + lxml | ≥4.12 / ≥5.2 | para los 4 scrapers HTML |
| Headless (reserva) | Playwright + stealth | ≥1.44 | no usado actualmente, disponible |
| ORM | SQLAlchemy 2.0 async | ≥2.0 | con asyncpg |
| BD | PostgreSQL | 12+ | base `carflip` |
| Migraciones | Alembic | ≥1.13 | versionado de schema |
| Config | pydantic-settings | ≥2.3 | lee `.env` |
| Scheduler | APScheduler | ≥3.10 | intervalo configurable |
| Logging | loguru | ≥0.7 | rotación automática |
| CLI | click | ≥8.1 | subcomandos: run, start, market |
| Tests | pytest + asyncio + mock | ≥8.2 | espeja src/ |

**Dependencias eliminadas** (respecto a v0.1.0):
- `keyring` — ya no se usan credenciales del OS
- `boto3` — ya no se usa AWS Secrets Manager
- `cryptography` (Fernet) — ya no se cifran cookies

---

## Configuración (.env)

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/carflip

# MercadoLibre API
MERCADOLIBRE_APP_ID=tu_app_id
MERCADOLIBRE_CLIENT_SECRET=tu_client_secret

# Delays entre requests (rate limiting)
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Scheduler
SCRAPE_INTERVAL_HOURS=6

# Detección de deals
DEAL_THRESHOLD_PCT=15.0

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log
```

Simplificación respecto a v0.1.0: se eliminan `use_secrets_manager`, `aws_region`, `secrets_manager_prefix` y toda referencia a keyring/Fernet.

---

## CLI

```bash
# Instalar dependencias
uv sync

# Aplicar migraciones
alembic upgrade head

# Ejecutar scrapers una vez (+ guardar CSV backup + upsert a BD)
carflip run

# Iniciar scheduler automático (primer ciclo inmediato, luego cada 6h)
carflip start

# Estadísticas de mercado
carflip market Toyota Corolla 2020

# Tests
pytest
pytest -x -v tests/test_price_tracker.py
pytest --cov=src/carflip
```

---

## Base de datos

### Diseño: tabla por scraper

Cada scraper tiene su propia tabla en Supabase. No existe una tabla `listings` unificada. El esquema compartido viene de `ListingMixin` en `src/carflip/database/models.py`.

**Tablas activas de avisos** (mismas columnas vía `ListingMixin`):
- `autocosmos_listings`
- `mercadolibre_listings`

Para agregar un nuevo scraper: crear `NuevoSitioListing(ListingMixin, Base)` + migración Alembic + declarar `model_class` en el scraper.

**Columnas de cada tabla de avisos** (`ListingMixin`):

| Columna | Tipo | Notas |
|---------|------|-------|
| id | BigInteger PK | autoincrement |
| id_externo | String(200) | ID único del aviso, clave de upsert |
| url | Text | link al aviso original |
| titulo | Text | título del aviso |
| precio | Numeric(14,2) | precio actual, indexado |
| moneda | String(10) | default "CLP" |
| marca | String(100) | marca, indexado |
| modelo | String(100) | modelo, indexado |
| anio | Integer | año, indexado |
| km | Integer | kilometraje |
| ubicacion | String(200) | ciudad / región |
| combustible | String(50) | bencina, diesel, eléctrico, etc. |
| descripcion | Text | descripción libre |
| url_imagen | Text | URL de la imagen principal |
| disponible | Boolean | si el aviso sigue activo |
| fecha_publicacion | String(50) | fecha del aviso en la fuente |
| precio_anterior | Numeric(14,2) | precio antes del último cambio |
| delta_pct | Float | % cambio de precio (negativo = bajó) |
| primera_vez_visto | DateTime(tz) | primera inserción |
| ultima_vez_visto | DateTime(tz) | última actualización |

Clave única: `id_externo` (por tabla). El upsert se gestiona en `src/carflip/database/uploader.py`.

**scrape_runs** — bitácora de ejecuciones

| Columna | Tipo | Notas |
|---------|------|-------|
| id | BigInteger PK | autoincrement |
| source | String(50) | fuente |
| started_at | DateTime(tz) | inicio |
| finished_at | DateTime(tz) | fin |
| items_found | Integer | avisos obtenidos |
| errors | Integer | errores en el ciclo |

**session_cookies** — cookies cifradas (reserva para scrapers con login).

---

## Validaciones del caso CarFlip (PDF)

El PDF define reglas de validación que deben implementarse como paso intermedio antes del upsert:

### Validación estructural

- `anio`: entero de 4 dígitos
- `precio`: entero > 0
- `km`: entero ≥ 0
- `fecha_publicacion`: formato YYYY-MM-DD
- `patente` (si aplica): formato chileno (XX1234 o XXXX12)

### Validación semántica

- `anio`: entre 1990 y año actual
- `precio`: entre $500.000 y $100.000.000 CLP
- `fecha_publicacion`: no puede ser futura
- `km` + `anio ≥ 2022`: si km > 100.000 → advertencia (no invalida)

### Dónde aplicar

En la arquitectura híbrida, la validación se aplica después del scrape y antes del upsert. Los avisos que no pasan validación se loggean pero no se insertan en la BD. El CSV raw los conserva tal cual para auditoría.

---

## Convenciones de código

### Naming

| Elemento | Convención | Ejemplo |
|----------|-----------|---------|
| Módulos | snake_case | `price_tracker.py` |
| Variables | snake_case | `avisos_obtenidos` |
| Clases | PascalCase | `ScraperBase`, `AvisoAuto` |
| Constantes | UPPER_SNAKE | `DEAL_THRESHOLD` |
| Scrapers | nombre del dominio | `mercadolibre.py`, `autocosmos.py` |
| Idioma | Español | `ejecutar()`, `espera_aleatoria()`, `fuente` |

### Typing

Type hints en todas las funciones. Preferir `X | None` sobre `Optional[X]`. Prohibido `# type: ignore` sin comentario que justifique.

### Async

Todo acceso a BD es async. `asyncio.run()` solo en `__main__.py`. Nunca dentro de coroutines.

### Logging

`loguru.logger` siempre. Nunca `print()`. Formato: `[{fuente}] mensaje`.

### Imports

```python
# stdlib
import asyncio

# terceros
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

# proyecto
from carflip.config import settings
from carflip.scrapers.base import AvisoAuto, ResultadoScraping
```

---

## Roadmap: de v0.1.0 al estado objetivo

### Fase 1 — Limpieza (prioridad alta)

- [ ] Eliminar `yapo.py`, `chileautos.py`, `facebook.py`
- [ ] Eliminar `credentials.py` y todo el sistema keyring/Fernet/AWS
- [ ] Eliminar subcomando `credentials` del CLI
- [ ] Corregir `pyproject.toml`: paquete `carflip`, no `carflipper`
- [ ] Corregir `price_tracker.py`: importar `AvisoAuto`/`ResultadoScraping` (no `CarListing`/`ScrapeResult`)
- [ ] Corregir `runner.py`: llamar `ejecutar()` (no `run()`)
- [ ] Eliminar `boto3` y `keyring` de dependencias
- [ ] Simplificar `config.py`: eliminar `use_secrets_manager`, `aws_region`, etc.
- [ ] Migración Alembic: eliminar tabla `session_cookies`

### Fase 2 — Nuevos scrapers (prioridad alta)

- [ ] Implementar `autocosmos.py` (httpx + BS4)
- [ ] Implementar `checkeados.py` (httpx + BS4)
- [ ] Implementar `economicos.py` (httpx + BS4)
- [ ] Verificar/actualizar `mercadolibre.py` (API)
- [ ] Verificar/actualizar `autosusados.py` (HTML)
- [ ] Actualizar `runner.py` con los 5 scrapers nuevos

### Fase 3 — Arquitectura híbrida (prioridad media)

- [ ] Agregar lógica de guardado CSV raw en `data/raw/{fuente}_{fecha}.csv`
- [ ] Implementar validaciones estructurales y semánticas pre-upsert
- [ ] Loggear avisos rechazados con razón de rechazo
- [ ] Reescribir `CLAUDE.md` para reflejar estado real
- [ ] Actualizar `README.md`
- [ ] Actualizar `CHANGELOG.md` con v0.2.0

### Fase 4 — Mejoras (prioridad baja)

- [ ] Dashboard o API REST para consultar datos
- [ ] Alertas de deals (notificaciones)
- [ ] Cobertura de tests > 80%
- [ ] CI/CD pipeline

---

## Referencias

- PDF del caso: `Caso CarFlip – Pipeline de Datos de Avisos de Autos`
- Repo datos autos USA: https://github.com/abhionlyone/us-car-models-data
- MercadoLibre API: https://developers.mercadolibre.com.ar/
- BeautifulSoup docs: https://www.crummy.com/software/BeautifulSoup/

---

*Última actualización: 2026-05-11 — v0.2.0-dev*