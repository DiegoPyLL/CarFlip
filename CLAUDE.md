# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

---

## Comandos

```bash
uv sync                                             # instalar / actualizar dependencias
alembic upgrade head                                # aplicar migraciones
alembic revision --autogenerate -m "descripcion"   # generar nueva migración
carflipper run                                      # ejecutar todos los scrapers una vez
carflipper start                                    # iniciar scheduler automático (cada 6h)
carflipper credentials set <source> <email> <pass> # guardar credenciales en el llavero del OS
carflipper credentials delete <source>             # eliminar credenciales
carflipper credentials list                        # ver qué sitios tienen credenciales
carflipper market <brand> <model> <year>           # estadísticas de mercado
pytest                                             # correr tests
pytest -x -v tests/test_price_tracker.py          # test específico con detalle
```

El `.venv` está en la raíz del proyecto. Usar siempre `.venv\Scripts\python` (Windows) como intérprete. VS Code debe tener seleccionado este intérprete.

PostgreSQL debe estar corriendo con la base de datos `carflipper` creada antes de ejecutar migraciones o el scraper.

No hay linter configurado aún. El type check se puede correr con `mypy src/` si se instala mypy como dependencia de desarrollo.

---

## Arquitectura

### Patrón de scrapers

Todos los scrapers heredan de `BaseScraper` en [src/carflipper/scrapers/base.py](src/carflipper/scrapers/base.py). El método abstracto a implementar es `scrape() -> list[CarListing]`. El método `run()` de la clase base gestiona logging, timing y manejo de errores — no sobreescribirlo.

`CarListing` es el modelo normalizado de salida. Todo scraper debe mapear sus datos al mismo dataclass, independiente del formato de origen.

Siempre llamar `await self.random_delay()` entre requests para respetar el rate limiting. El rango de delay está en `settings.min_delay_seconds` / `settings.max_delay_seconds`.

### Scrapers HTTP vs. Playwright

- **httpx + BeautifulSoup4**: para sitios que sirven HTML estático o APIs REST (MercadoLibre usa su API oficial).
- **Playwright** (headless Chromium + playwright-stealth): para sitios con JavaScript o que requieren login (Facebook Marketplace).

Nunca usar Playwright donde alcanza httpx — es más lento y consume más recursos.

### Credenciales y sesiones

Dos mecanismos, cada uno para un propósito distinto — no mezclarlos:

- **keyring** (`credentials.py`): passwords de usuarios en el Windows Credential Manager. Nunca escribir passwords en archivos, variables de entorno ni logs.
- **Fernet + PostgreSQL** (`session_cookies`): cookies de sesión del browser cifradas. La clave Fernet también se guarda en el llavero del OS, nunca en `.env`.

### Base de datos

ORM: SQLAlchemy 2.0 async con `AsyncSession`. Siempre usar el context manager de `AsyncSessionLocal` de [src/carflipper/database/session.py](src/carflipper/database/session.py).

Modelos en [src/carflipper/database/models.py](src/carflipper/database/models.py):
- `Listing` — aviso normalizado (upsert por `source` + `external_id`)
- `PriceHistory` — historial de precios con `delta_pct`
- `ScrapedRun` — log de ejecuciones por fuente
- `SessionCookie` — cookies cifradas por fuente

Toda modificación de esquema va por Alembic. Nunca modificar tablas con DDL directo en producción.

### Scheduler

APScheduler ejecuta `run_all_scrapers()` cada `scrape_interval_hours` horas (default 6). El primer ciclo corre de forma inmediata al hacer `carflipper start`, antes de registrar el job.

### Configuración

`pydantic-settings` lee desde `.env`. Variables disponibles en [src/carflipper/config.py](src/carflipper/config.py). El objeto `settings` es un singleton importable desde cualquier módulo.

---

## Stack

- **Python** 3.12+, gestionado con **uv**
- **Scraping HTTP**: httpx + BeautifulSoup4 + lxml
- **Scraping headless**: Playwright + playwright-stealth + fake-useragent
- **ORM / DB**: SQLAlchemy 2.0 async, asyncpg, Alembic
- **Validación / config**: pydantic 2, pydantic-settings
- **Scheduler**: APScheduler 3
- **Credenciales**: keyring, cryptography (Fernet)
- **Logging**: loguru
- **CLI**: click
- **Tests**: pytest + pytest-asyncio + pytest-mock

---

## Convenciones de código

### Naming

- Módulos y variables: `snake_case`
- Clases: `PascalCase`
- Constantes de módulo: `UPPER_SNAKE_CASE`
- Scrapers: nombrar el archivo por el dominio scrapeado (`yapo.py`, `chileautos.py`)

### Typing

Usar type hints en todas las funciones. Prohibido `# type: ignore` salvo casos estrictamente documentados con un comentario que explique por qué. Preferir `X | None` sobre `Optional[X]` (Python 3.10+ union syntax).

### Async

Todo acceso a la base de datos es `async`. No mezclar código `asyncio.run()` dentro de coroutines — `asyncio.run()` solo en el punto de entrada del CLI.

### Logging

Usar siempre `loguru.logger`. Nunca `print()` en código de producción. Niveles:
- `logger.info` — inicio/fin de scrape, credenciales guardadas
- `logger.debug` — cookies, detalles de requests
- `logger.warning` — credenciales no encontradas, datos faltantes recuperables
- `logger.error` — errores fatales por fuente
- `logger.exception` — dentro de except cuando se quiere el traceback completo

Nunca loggear passwords, cookies en texto plano ni claves Fernet.

---

## Seguridad

### Credenciales

- Passwords: exclusivamente via `keyring`. Nunca en `.env`, logs, ni variables de entorno.
- La clave Fernet se genera y recupera desde el llavero del OS — nunca persistirla en disco ni en `.env`.
- `.env` solo para configuración no sensible: `DATABASE_URL`, `MERCADOLIBRE_APP_ID`, umbrales. `MERCADOLIBRE_CLIENT_SECRET` es la excepción aceptada porque la API de ML lo requiere como env var.

### Errores — nunca exponer internos

Capturar excepciones en `BaseScraper.run()` ya maneja el caso general. En código nuevo, loggear el error real con `logger.error` / `logger.exception` en el servidor; nunca propagar stack traces ni mensajes de DB a la salida del CLI más allá de un mensaje genérico.

### Rate limiting y detección

- Siempre `await self.random_delay()` entre requests.
- Usar `fake-useragent` para rotar User-Agent en scrapers HTTP.
- Playwright con `playwright-stealth` para sitios que detectan headless.
- No paralelizar requests al mismo dominio sin throttling explícito — riesgo de ban de IP.

### SQL

Nunca construir queries concatenando strings. Usar siempre SQLAlchemy ORM o `text()` con parámetros vinculados (`:param`). Nunca interpolar input externo en SQL.

---

## Tests

Tests en `tests/`. Estructura espeja `src/carflipper/`.

- **No mockear la base de datos** en tests de integración — usar una DB de test real (`carflipper_test`). Los tests que requieren DB deben estar marcados y documentados.
- Para tests unitarios de scrapers: mockear las respuestas HTTP con `pytest-mock` o `respx` (httpx), no la DB.
- Usar `pytest-asyncio` para coroutines: decorar con `@pytest.mark.asyncio`.
- No testear la lógica interna de Playwright directamente — demasiado frágil. Testear el parsing de HTML con fixtures de HTML estático.

---

## Migraciones (Alembic)

- Una migración por cambio lógico. No agrupar migraciones no relacionadas.
- Siempre revisar el archivo generado por `--autogenerate` antes de aplicarlo — Alembic no detecta todo correctamente (índices parciales, funciones, vistas).
- La vista `v_market_comparison` se gestiona manualmente en migraciones, no por autogenerate.
- Nunca modificar una migración ya aplicada en producción — crear una nueva que revierta o ajuste.

---

## Versionamiento

### Branching

Rama principal: `main`. Siempre estable y ejecutable.

Para cualquier cambio que no sea un fix trivial de una línea, crear una rama de trabajo:

```
feat/nombre-scraper       # nuevo scraper o funcionalidad
fix/descripcion-bug       # corrección de bug
chore/descripcion         # dependencias, config, refactor sin cambio de comportamiento
db/descripcion-migracion  # cambios de esquema (siempre acompañados de su migración Alembic)
```

Mergear a `main` cuando los tests pasan y el scraper fue probado manualmente al menos una vez.

### Commits — Conventional Commits

Formato: `<tipo>(<scope opcional>): <descripción en imperativo>`

| Tipo | Cuándo usarlo |
|------|--------------|
| `feat` | nuevo scraper, nuevo comando CLI, nueva funcionalidad observable |
| `fix` | corrección de bug en scraping, parsing, DB o scheduler |
| `chore` | actualización de dependencias, config, sin cambio de comportamiento |
| `refactor` | restructuración interna sin cambio de funcionalidad |
| `test` | agregar o corregir tests |
| `db` | migración de base de datos |
| `docs` | cambios en CLAUDE.md u otro documento |

Ejemplos válidos:
```
feat(yapo): agregar soporte para filtro de año en búsqueda
fix(facebook): manejar timeout en login con Playwright
chore: actualizar httpx a 0.28
db: agregar índice compuesto source+brand+model en listings
test(price_tracker): agregar test de detección de deal
```

Descripción en minúsculas, sin punto final, en español. Una sola línea salvo que el cambio sea complejo — en ese caso, cuerpo separado por línea en blanco.

No commitear `.env`, `logs/`, ni archivos generados por `alembic/versions/` sin su migración correspondiente.

### CHANGELOG

El proyecto mantiene un archivo [CHANGELOG.md](CHANGELOG.md) en el formato de [Keep a Changelog](https://keepachangelog.com/). **Toda versión que se cree debe actualizarse en el CHANGELOG antes de mergear a `main`.**

Estructura del CHANGELOG:
- Una sección `## [VERSION] - YYYY-MM-DD` por cada versión
- Subsecciones: `### Added`, `### Changed`, `### Fixed`, `### Removed`, `### Deprecated`
- Descripciones claras y observables desde la perspectiva del usuario
- Agrupar por categoría, no por archivo

Ejemplo de entrada:
```markdown
## [0.2.0] - 2026-05-15

### Added
- Nuevo scraper `olx.py` para Olx Chile
- Comando `carflipper market` para estadísticas de mercado

### Fixed
- Manejar timeout en Facebook Marketplace durante login
- Corregir parseo de precios con miles separator en Yapo

### Changed
- Aumentar delay mínimo entre requests de 2s a 3s
```

### Versión del paquete (`pyproject.toml`)

El proyecto sigue **Semantic Versioning** (`MAJOR.MINOR.PATCH`). Versión actual: `0.1.0`.

| Cambio | Qué bumpar |
|--------|-----------|
| Bug fix, mejora de estabilidad | `PATCH` → `0.1.1` |
| Nuevo scraper, nuevo comando CLI, nueva feature | `MINOR` → `0.2.0` |
| Cambio en la interfaz del CLI o esquema de DB incompatible hacia atrás | `MAJOR` → `1.0.0` |

Mientras el proyecto sea `0.x.y`, los cambios de `MINOR` pueden incluir breaking changes.

Actualizar la versión en `pyproject.toml` antes de mergear a `main`. Crear un tag anotado en ese commit:

```bash
git tag -a v0.2.0 -m "feat: soporte Facebook Marketplace"
git push origin v0.2.0
```

### Lo que no va en git

Confirmado por `.gitignore`:
- `.env` — variables de entorno y configuración local
- `.venv/` — entorno virtual (reproducible con `uv sync`)
- `logs/` — archivos de log rotativos
- `__pycache__/`, `*.pyc` — artefactos de Python
- `dist/`, `build/` — artefactos de empaquetado

No agregar excepciones al `.gitignore` sin justificación explícita.

---

## Prohibiciones

- No `print()` en ningún módulo de `src/` — usar `logger`.
- No passwords ni claves Fernet en `.env`, archivos de configuración ni logs.
- No queries SQL con concatenación de strings — siempre parámetros vinculados.
- No `asyncio.run()` dentro de coroutines.
- No Playwright donde alcanza httpx.
- No paralelizar requests al mismo dominio sin delay explícito entre ellos.
- No modificar migraciones ya aplicadas — crear una nueva.
- No `# type: ignore` sin comentario que explique el motivo.
- No sobreescribir `BaseScraper.run()` — solo implementar `scrape()`.
