# GEMINI.md

Documento unificado de instrucciones y referencias para el desarrollo de CarFlip.

---

## Qué es CarFlip

Plataforma que agrega avisos de autos en venta desde 5 portales chilenos, normaliza los datos, los persiste en PostgreSQL y detecta oportunidades de compra (deals) mediante análisis de historial de precios.

---

## Decisiones de diseño

Estas decisiones se tomaron el 2026-05-11 y rigen todo el desarrollo futuro:

| Tema               | Decisión                                                                                                                   |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Naming del código | Todo en español:`AvisoAuto`, `ScraperBase`, `ejecutar()`, `espera_aleatoria()`                                     |
| Arquitectura       | EC2 + TMUX + APScheduler: N scrapers paralelos en sesiones TMUX independientes                                              |
| Almacenamiento raw | `data/raw/` local en EC2 (efímero) — Cloudflare R2 recibe imágenes AVIF validadas; PostgreSQL recibe metadata validada |
| Base de datos      | PostgreSQL async (SQLAlchemy 2.0 + asyncpg + Alembic)                                                                       |
| Scraping HTTP      | httpx + BeautifulSoup4 + lxml para los 5 sitios                                                                             |
| Scraping headless  | Playwright + stealth se mantiene en dependencias como reserva                                                               |
| Credenciales       | Solo `.env` — eliminar keyring, Fernet, AWS Secrets Manager                                                              |
| CLI                | Mantener click:`carflip run`, `carflip start`, `carflip market`                                                       |
| Logging            | loguru (no `print()` nunca)                                                                                               |
| Tests              | pytest + pytest-asyncio + pytest-mock                                                                                       |
| Gestor de paquetes | uv                                                                                                                          |

---

## Comandos

```bash
uv sync                                             # instalar / actualizar dependencias
alembic upgrade head                                # aplicar migraciones
alembic revision --autogenerate -m "descripcion"   # generar nueva migración
carflip run                                         # ejecutar todos los scrapers una vez
carflip start                                       # iniciar scheduler automático (cada 6h)
carflip market <brand> <model> <year>              # estadísticas de mercado
pytest                                             # correr tests
pytest -x -v tests/test_price_tracker.py          # test específico con detalle
```

El `.venv` está en la raíz del proyecto. Usar siempre `.venv\Scripts\python` (Windows) como intérprete. VS Code debe tener seleccionado este intérprete.

PostgreSQL debe estar corriendo con la base de datos `carflip` creada antes de ejecutar migraciones o el scraper.

No hay linter configurado aún. El type check se puede correr con `mypy src/` si se instala mypy como dependencia de desarrollo.

---

## Arquitectura

### Pipeline completo

```
INGESTA (EC2 + TMUX)
────────────────────
APScheduler lanza N scrapers (uno por portal) como subprocesos en sesiones TMUX separadas.
Cada scraper ejecuta ScraperBase.ejecutar() que:
  1. scraper.scrape() → retorna list[AvisoAuto]
  2. Serializa cada aviso a JSON y guarda fotos en formato original

Output por scraper: fotos (formato original) + metadata.json
Guardado en: data/raw/{fuente}_{fecha}/ en EC2 (efímero)
Batch upload en cola por página

El upsert a PostgreSQL NO ocurre en esta etapa — ocurre al final del pipeline,
después de limpieza y validación.


LIMPIEZA Y TRANSFORMACIÓN (pipeline ETL)
─────────────────────────────────────────
Fotos:
  1. Deduplicación de imágenes
       └─ FAIL LOG si error: {timestamp, etapa="dedup_fotos", motivo, id_externo, fuente}
  2. Conversión a AVIF (si no están en AVIF)
       └─ FAIL LOG si conversión falla: {timestamp, etapa="conversion_avif", motivo, id_externo, fuente}

Metadata JSON:
  1. Deduplicación por id_externo
       └─ FAIL LOG si error: {timestamp, etapa="dedup_json", motivo, id_externo, fuente}


VALIDACIÓN
──────────
AVIF + JSON pasan por validación de campos (estructural y semántica, ver sección Validaciones)
  └─ FAIL LOG si falla: {timestamp, etapa="validacion_avif"|"validacion_json", motivo, id_externo, fuente}


CARGA
─────
FAIL LOGs → audit store (consolidados)
AVIF validadas → Cloudflare R2 CDN (retry x5 durante 2 horas)
JSON validado  → PostgreSQL via upsert (retry x5 durante 2 horas)
Visualización  → Vercel (consume PostgreSQL)
```

### Patrón de scrapers

Todos los scrapers heredan de `ScraperBase` en `src/carflip/scrapers/base.py`. El único método a implementar es `scrape() -> list[AvisoAuto]`. El método `ejecutar()` de la clase base gestiona logging, timing, manejo de errores y el upload automático a PostgreSQL — no sobreescribirlo.

Cada scraper declara un atributo de clase `model_class` apuntando a su modelo SQLAlchemy (tabla en PostgreSQL). Sin `model_class`, `ejecutar()` igual funciona pero no sube a la BD:

```python
class ScraperAutocosmos(ScraperBase):
    fuente = "autocosmos"
    model_class = AutocosmosListing  # → tabla autocosmos_listings

    async def scrape(self) -> list[AvisoAuto]:
        ...
```

Siempre llamar `await self.espera_aleatoria()` entre requests para respetar el rate limiting. El rango de delay está en `settings.min_delay_seconds` / `settings.max_delay_seconds`.

### Scrapers HTTP vs. Playwright

- **httpx + BeautifulSoup4**: para sitios que sirven HTML estático o APIs REST (MercadoLibre usa su API oficial).
- **Playwright** (headless Chromium + playwright-stealth): reserva para sitios con JavaScript o que requieren login (no usado actualmente).

Nunca usar Playwright donde alcanza httpx — es más lento y consume más recursos.

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

## Fuentes de datos

### 1. MercadoLibre — `api.mercadolibre.com`

| Propiedad    | Valor                                                                          |
| ------------ | ------------------------------------------------------------------------------ |
| Tipo         | API REST oficial                                                               |
| Formato      | JSON estructurado                                                              |
| Auth         | Token via `MERCADOLIBRE_APP_ID` + `MERCADOLIBRE_CLIENT_SECRET` en `.env` |
| Herramientas | `httpx` (sin BS4 necesario)                                                  |
| Volumen      | Alto                                                                           |
| Anti-bot     | Rate limiting de la API                                                        |

Es el único sitio donde no se escribe un scraper HTML sino un cliente HTTP contra endpoints JSON. Los campos ya vienen normalizados.

### 2. Autocosmos — `autocosmos.cl`

| Propiedad    | Valor                            |
| ------------ | -------------------------------- |
| Tipo         | HTML server-side (PHP)           |
| Formato      | DOM estable y predecible         |
| Auth         | Ninguna                          |
| Herramientas | `httpx` + `BeautifulSoup4`   |
| Volumen      | Medio                            |
| Anti-bot     | Sin Cloudflare, sin JS necesario |

### 3. Autosusados — `autosusados.cl`

| Propiedad    | Valor                          |
| ------------ | ------------------------------ |
| Tipo         | HTML server-side               |
| Formato      | Estructura limpia              |
| Auth         | Ninguna                        |
| Herramientas | `httpx` + `BeautifulSoup4` |
| Volumen      | Medio-Bajo                     |
| Anti-bot     | Sin protecciones apreciables   |

### 4. Checkeados — `checkeados.cl`

| Propiedad    | Valor                          |
| ------------ | ------------------------------ |
| Tipo         | HTML server-side               |
| Formato      | DOM sencillo                   |
| Auth         | Ninguna                        |
| Herramientas | `httpx` + `BeautifulSoup4` |
| Volumen      | Bajo (automotora única)       |
| Anti-bot     | Protección nula               |

### 5. Económicos — `economicos.cl`

| Propiedad    | Valor                                |
| ------------ | ------------------------------------ |
| Tipo         | HTML server-side (grupo El Mercurio) |
| Formato      | DOM estándar                        |
| Auth         | Ninguna                              |
| Herramientas | `httpx` + `BeautifulSoup4`       |
| Volumen      | Medio                                |
| Anti-bot     | Sin Cloudflare                       |

Particularidad: incluye particulares además de automotoras, lo que aporta variedad al dataset.

---

## Stack

| Componente         | Tecnología             | Versión       | Notas                            |
| ------------------ | ----------------------- | -------------- | -------------------------------- |
| Lenguaje           | Python                  | 3.12+          | gestionado con uv                |
| HTTP               | httpx                   | ≥0.27         | async, para todos los scrapers   |
| HTML Parser        | BeautifulSoup4 + lxml   | ≥4.12 / ≥5.2 | para los 4 scrapers HTML         |
| Headless (reserva) | Playwright + stealth    | ≥1.44         | disponible, no usado actualmente |
| ORM                | SQLAlchemy 2.0 async    | ≥2.0          | con asyncpg                      |
| BD                 | PostgreSQL              | 12+            | base `carflip`                 |
| Migraciones        | Alembic                 | ≥1.13         | versionado de schema             |
| Config             | pydantic-settings       | ≥2.3          | lee `.env`                     |
| Scheduler          | APScheduler             | ≥3.10         | intervalo configurable           |
| Logging            | loguru                  | ≥0.7          | rotación automática            |
| CLI                | click                   | ≥8.1          | subcomandos: run, start, market  |
| Tests              | pytest + asyncio + mock | ≥8.2          | espeja src/                      |

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

## Base de datos

### Diseño: tabla por scraper

Cada scraper tiene su propia tabla en PostgreSQL. No existe una tabla `listings` unificada. El esquema compartido viene de `ListingMixin` en `src/carflip/database/models.py`.

**Tablas activas de avisos** (mismas columnas vía `ListingMixin`):

- `autocosmos_listings`
- `mercadolibre_listings`
- `autosusados_listings`
- `checkeados_listings`
- `economicos_listings`

Para agregar un nuevo scraper: crear `NuevoSitioListing(ListingMixin, Base)` + migración Alembic + declarar `model_class` en el scraper.

**Columnas de cada tabla de avisos** (`ListingMixin`):

| Columna           | Tipo          | Notas                                 |
| ----------------- | ------------- | ------------------------------------- |
| id                | BigInteger PK | autoincrement                         |
| id_externo        | String(200)   | ID único del aviso, clave de upsert  |
| url               | Text          | link al aviso original                |
| titulo            | Text          | título del aviso                     |
| precio            | Numeric(14,2) | precio actual, indexado               |
| moneda            | String(10)    | default "CLP"                         |
| marca             | String(100)   | marca, indexado                       |
| modelo            | String(100)   | modelo, indexado                      |
| anio              | Integer       | año, indexado                        |
| km                | Integer       | kilometraje                           |
| ubicacion         | String(200)   | ciudad / región                      |
| combustible       | String(50)    | bencina, diesel, eléctrico, etc.     |
| descripcion       | Text          | descripción libre                    |
| url_imagen        | Text          | URL de la imagen principal            |
| disponible        | Boolean       | si el aviso sigue activo              |
| fecha_publicacion | String(50)    | fecha del aviso en la fuente          |
| precio_anterior   | Numeric(14,2) | precio antes del último cambio       |
| delta_pct         | Float         | % cambio de precio (negativo = bajó) |
| primera_vez_visto | DateTime(tz)  | primera inserción                    |
| ultima_vez_visto  | DateTime(tz)  | última actualización                |

Clave única: `id_externo` (por tabla). El upsert se gestiona en `src/carflip/database/uploader.py`.

**scrape_runs** — bitácora de ejecuciones

| Columna     | Tipo          | Notas               |
| ----------- | ------------- | ------------------- |
| id          | BigInteger PK | autoincrement       |
| source      | String(50)    | fuente              |
| started_at  | DateTime(tz)  | inicio              |
| finished_at | DateTime(tz)  | fin                 |
| items_found | Integer       | avisos obtenidos    |
| errors      | Integer       | errores en el ciclo |

---

## Validaciones

El pipeline aplica validaciones estructurales y semánticas antes de la carga. Los avisos que no pasan son loggados con FAIL LOG pero no se insertan en la BD ni se suben a R2. Los FAIL LOGs se consolidan en el audit store para auditoría.

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

---

## Convenciones de código

### Naming

| Elemento   | Convención        | Ejemplo                                            |
| ---------- | ------------------ | -------------------------------------------------- |
| Módulos   | snake_case         | `price_tracker.py`                               |
| Variables  | snake_case         | `avisos_obtenidos`                               |
| Clases     | PascalCase         | `ScraperBase`, `AvisoAuto`                     |
| Constantes | UPPER_SNAKE        | `DEAL_THRESHOLD`                                 |
| Scrapers   | nombre del dominio | `mercadolibre.py`, `autocosmos.py`             |
| Idioma     | Español           | `ejecutar()`, `espera_aleatoria()`, `fuente` |

### Typing

Type hints en todas las funciones. Preferir `X | None` sobre `Optional[X]`. Prohibido `# type: ignore` sin comentario que justifique.

### Async

Todo acceso a BD es async. `asyncio.run()` solo en `__main__.py`. Nunca dentro de coroutines.

### Logging

Usar siempre `loguru.logger`. Nunca `print()` en código de producción.

**Logging por etapa del pipeline:**

Ingesta (scraper):

- `logger.info` — inicio/fin de scrape, conteo de avisos obtenidos, duración
- `logger.debug` — detalles de cada request HTTP (URL, status code)
- `logger.warning` — campo faltante o dato recuperable (ej. km no encontrado)
- `logger.error` — fallo fatal del scraper (timeout, estructura DOM cambiada)
- `logger.exception` — dentro de except cuando se quiere el traceback completo

Limpieza:

- `logger.warning` — duplicado detectado, conversión AVIF iniciada
- `logger.error` — fallo conversión AVIF, error en deduplicación JSON

Validación:

- `logger.warning` — campo inválido encontrado, valor fuera de rango
- `logger.error` — aviso rechazado por validación, razón específica

Carga:

- `logger.info` — upsert exitoso, conteo de inserciones/actualizaciones
- `logger.warning` — reintento fallido (1-4), notificación de retry
- `logger.exception` — agotados reintentos, operación abortada

**Nunca loggear:**

- Passwords, tokens de API, strings de conexión a BD
- Cookies en texto plano
- Payloads completos de respuestas HTTP (solo IDs y counts)

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

## Seguridad

### Credenciales

- Credenciales: exclusivamente en `.env` — eliminados keyring, Fernet, AWS Secrets Manager
- `.env` contiene: `DATABASE_URL`, `MERCADOLIBRE_APP_ID`, `MERCADOLIBRE_CLIENT_SECRET`, delays, thresholds
- `MERCADOLIBRE_CLIENT_SECRET` es la única clave sensible aceptada en `.env` (requerido por la API de ML)
- Nunca en logs ni en output del CLI: passwords, tokens, conexión a BD

### Errores — nunca exponer internos

Capturar excepciones en `BaseScraper.ejecutar()` ya maneja el caso general. En código nuevo, loggear el error real con `logger.error` / `logger.exception` en el servidor; nunca propagar stack traces ni mensajes de DB a la salida del CLI más allá de un mensaje genérico.

### Rate limiting y detección

- Siempre `await self.espera_aleatoria()` entre requests.
- Usar `fake-useragent` para rotar User-Agent en scrapers HTTP.
- Playwright con `playwright-stealth` para sitios que detectan headless (si se utiliza).
- No paralelizar requests al mismo dominio sin throttling explícito — riesgo de ban de IP.

### SQL

Nunca construir queries concatenando strings. Usar siempre SQLAlchemy ORM o `text()` con parámetros vinculados (`:param`). Nunca interpolar input externo en SQL.

---

## Tests

Tests en `tests/`. Estructura espeja `src/carflip/`.

- **No mockear la base de datos** en tests de integración — usar una DB de test real (`carflip_test`). Los tests que requieren DB deben estar marcados y documentados.
- Para tests unitarios de scrapers: mockear las respuestas HTTP con `pytest-mock` o `respx` (httpx), no la DB.
- Usar `pytest-asyncio` para coroutines: decorar con `@pytest.mark.asyncio`.
- No testear la lógica interna de Playwright directamente — demasiado frágil. Testear el parsing de HTML con fixtures de HTML estático.

---

## Migraciones (Alembic)

- Una migración por cambio lógico. No agrupar migraciones no relacionadas.
- Siempre revisar el archivo generado por `--autogenerate` antes de aplicarlo — Alembic no detecta todo correctamente (índices parciales, funciones, vistas).
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

| Tipo         | Cuándo usarlo                                                       |
| ------------ | -------------------------------------------------------------------- |
| `feat`     | nuevo scraper, nuevo comando CLI, nueva funcionalidad observable     |
| `fix`      | corrección de bug en scraping, parsing, DB o scheduler              |
| `chore`    | actualización de dependencias, config, sin cambio de comportamiento |
| `refactor` | restructuración interna sin cambio de funcionalidad                 |
| `test`     | agregar o corregir tests                                             |
| `db`       | migración de base de datos                                          |
| `docs`     | cambios en CLAUDE.md, gemini.md u otro documento                     |

Ejemplos válidos:

```
feat(checkeados): agregar nuevo scraper Checkeados
fix(autocosmos): manejar estructura DOM actualizada
chore: actualizar httpx a 0.28
db: agregar índice en mercadolibre_listings(marca, modelo)
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
## [0.2.0] - 2026-05-16

### Added
- Nuevo scraper `checkeados.py` para Checkeados Chile
- Nuevo scraper `economicos.py` para Económicos Chile
- Pipeline ETL completo: deduplicación → AVIF conversion → validación
- FAIL LOG consolidado para auditoría
- Comando `carflip market` para estadísticas de mercado

### Fixed
- Manejar cambios en DOM de Autocosmos
- Corregir parseo de precios en Autosusados

### Changed
- Migración a PostgreSQL desde Supabase
- Eliminar credenciales del OS (keyring) — solo .env
- Aumentar delay mínimo entre requests a 2s
```

### Versión del paquete (`pyproject.toml`)

El proyecto sigue **Semantic Versioning** (`MAJOR.MINOR.PATCH`). Versión actual: `0.1.0`.

| Cambio                                                                  | Qué bumpar            |
| ----------------------------------------------------------------------- | ---------------------- |
| Bug fix, mejora de estabilidad                                          | `PATCH` → `0.1.1` |
| Nuevo scraper, nuevo comando CLI, nueva feature                         | `MINOR` → `0.2.0` |
| Cambio en la interfaz del CLI o esquema de DB incompatible hacia atrás | `MAJOR` → `1.0.0` |

Mientras el proyecto sea `0.x.y`, los cambios de `MINOR` pueden incluir breaking changes.

Actualizar la versión en `pyproject.toml` antes de mergear a `main`. Crear un tag anotado en ese commit:

```bash
git tag -a v0.2.0 -m "feat: scrapers Checkeados y Económicos + pipeline ETL"
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
- No passwords ni claves en `.env` excepto `MERCADOLIBRE_CLIENT_SECRET` (requerido por API).
- No queries SQL con concatenación de strings — siempre parámetros vinculados.
- No `asyncio.run()` dentro de coroutines.
- No Playwright donde alcanza httpx.
- No paralelizar requests al mismo dominio sin delay explícito entre ellos.
- No modificar migraciones ya aplicadas — crear una nueva.
- No `# type: ignore` sin comentario que explique el motivo.
- No sobreescribir `BaseScraper.ejecutar()` — solo implementar `scrape()`.

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

### Fase 3 — Pipeline ETL (prioridad media)

- [ ] Agregar lógica de deduplicación de imágenes
- [ ] Agregar lógica de conversión a AVIF
- [ ] Agregar validaciones estructurales y semánticas pre-upsert
- [ ] Loggear FAIL LOGs consolidados con auditoría
- [ ] Actualizar `README.md`
- [ ] Actualizar `CHANGELOG.md` con v0.2.0

### Fase 4 — Mejoras (prioridad baja)

- [ ] Dashboard o API REST para consultar datos
- [ ] Alertas de deals (notificaciones)
- [ ] Cobertura de tests > 80%
- [ ] CI/CD pipeline

---

## Referencias

- Caso CarFlip — Pipeline de Datos de Avisos de Autos (PDF)
- Repo datos autos USA: https://github.com/abhionlyone/us-car-models-data
- MercadoLibre API: https://developers.mercadolibre.com.ar/
- BeautifulSoup docs: https://www.crummy.com/software/BeautifulSoup/

---

*Última actualización: 2026-05-16 — v0.2.0-dev*
