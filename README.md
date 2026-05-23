# CarFlip

Plataforma de inteligencia de mercado automotriz que agrega avisos de autos en venta desde múltiples portales chilenos, normaliza los datos, los persiste en PostgreSQL y detecta oportunidades de compra mediante análisis de historial de precios.

![CarFlip Logo](carflip_logo.png)

## Propuesta de Valor

- **Agregación centralizada**: Unifica precios, características y disponibilidad desde portales chilenos en una sola plataforma
- **Inteligencia en tiempo real**: Monitoreo automático cada 12 horas para identificar oportunidades de arbitraje y tendencias de precio
- **Análisis de historial**: Registro automático de cambios de precio con cálculo de deltas porcentuales
- **Pipeline de imágenes**: Descarga, conversión a AVIF y distribución vía CDN (Cloudflare R2)
- **Operaciones sin intervención**: Scheduler automático reduce costos y aumenta frecuencia de monitoreo

## Capacidades Técnicas

| Componente                   | Especificación                                                      |
| ---------------------------- | -------------------------------------------------------------------- |
| Fuentes activas              | Autocosmos (httpx + BS4), Yapo (Playwright)                          |
| Fuentes en roadmap           | MercadoLibre (API), Autosusados, Checkeados, Económicos             |
| Frecuencia de actualización | Configurable (default: cada 12 horas)                                |
| Historización de datos      | Deltas de precio calculados automáticamente en cada upsert          |
| Pipeline de imágenes        | Descarga → S3 → deduplicación → AVIF → Cloudflare R2 CDN        |
| Seguridad de credenciales    | Variables de entorno exclusivamente (`.env`)                       |
| Integridad de datos          | Normalización a `AvisoAuto`, upsert por `id_externo` por fuente |

## Requerimientos

- Python 3.12 o superior
- PostgreSQL 12+ con base de datos `carflip`
- uv (gestor de paquetes)

## Instalación

### 1. Preparación del entorno

```bash
# Clonar repositorio
git clone https://github.com/DiegoPyLL/CarFlip
cd carflip

# Instalar dependencias
uv sync

# Crear base de datos
createdb carflip
```

### 2. Configuración

Crear archivo `.env` en la raíz del proyecto:

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/carflip

# S3 (intermediario de fotos antes de R2)
S3_ACCESS_KEY_ID=tu_access_key
S3_SECRET_ACCESS_KEY=tu_secret_key
S3_REGION=us-east-1
S3_BUCKET=carflip-raw
S3_PREFIX=raw/

# Cloudflare R2 (CDN de imágenes finales)
R2_ACCOUNT_ID=tu_account_id
R2_BUCKET=carflip-fotos
R2_ACCESS_KEY_ID=tu_r2_access_key
R2_SECRET_ACCESS_KEY=tu_r2_secret_key
R2_PREFIX=autocosmos/fotos/

# Delays entre requests (rate limiting)
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Scheduler
SCRAPE_INTERVAL_HOURS=12

# Detección de deals
DEAL_THRESHOLD_PCT=15.0

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log
```

### 3. Aplicar esquema de base de datos

```bash
alembic upgrade head
```

## Uso

### Ejecución manual de scrapers

```bash
carflip run
```

Ejecuta un ciclo completo de scraping y persiste los datos en PostgreSQL. Si no se especifica scraper, muestra un menú interactivo.

```bash
# Ejecutar solo un scraper específico
carflip run --scraper autocosmos
```

### Activar scheduler automático

```bash
carflip start
```

Inicia el scheduler. El primer ciclo se ejecuta inmediatamente, los siguientes cada `SCRAPE_INTERVAL_HOURS` horas.

### Estadísticas de mercado

```bash
carflip market <marca> <modelo> <año>
```

Ejemplo:

```bash
carflip market Toyota Corolla 2020
```

Retorna precio promedio, mínimo, máximo y volumen de listados activos.

## Tests

```bash
# Suite completa
pytest

# Test específico con salida detallada
pytest -x -v tests/test_price_tracker.py

# Con cobertura de código
pytest --cov=src/carflip
```

## Arquitectura

### Flujo de Datos

```
Portal Web → HTTP (httpx) / Headless (Playwright)
    ↓
Parser (BeautifulSoup4 / JS extraction)
    ↓
Normalización (AvisoAuto dataclass)
    ↓ INGESTA
Descarga de fotos → S3 (con reintentos, hasta 2h)
    ↓ LIMPIEZA
Deduplicación por id_externo
    ↓ VALIDACIÓN
Validación estructural y semántica (precio, año, km, fecha)
    ↓ CARGA
PostgreSQL (upsert por id_externo, detección delta de precio)
    ↓ PIPELINE IMÁGENES
S3 → conversión AVIF → Cloudflare R2 CDN
    ↓
Estadísticas de mercado (price_tracker)
```

### Patrón de Scrapers

Todos los scrapers heredan de `ScraperBase` en [src/carflip/scrapers/base.py](src/carflip/scrapers/base.py). El único método a implementar es `scrape()`. La clase base gestiona logging, timing, manejo de errores y el upsert automático a PostgreSQL.

```python
class MiScraper(ScraperBase):
    fuente = "mi_fuente"
    model_class = MiFuenteListing  # tabla SQLAlchemy destino

    async def scrape(self) -> list[AvisoAuto]:
        avisos = []
        # lógica de scraping ...
        await self.espera_aleatoria()  # rate limiting
        return avisos
```

Nunca sobreescribir `ejecutar()` — solo implementar `scrape()`.

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

### Esquema de Base de Datos

Cada fuente tiene su propia tabla (sin tabla unificada). Todas comparten las mismas columnas vía `ListingMixin`.

| Tabla                   | Propósito                                       |
| ----------------------- | ------------------------------------------------ |
| `autocosmos_listings` | Avisos de Autocosmos (upsert por `id_externo`) |
| `yapo_listings`       | Avisos de Yapo (upsert por `id_externo`)       |
| `scrape_runs`         | Bitácora de ejecuciones por fuente              |

Columnas clave de cada tabla de avisos: `id_externo`, `precio`, `precio_anterior`, `delta_pct`, `primera_vez_visto`, `ultima_vez_visto`.

Para agregar una nueva fuente: crear `NuevoSitioListing(ListingMixin, Base)` + migración Alembic + declarar `model_class` en el scraper.

### Pipeline de Imágenes (S3 → R2) TODO("Actualizar según la estructura del R2")

Las fotos se descargan durante el scraping y se suben a S3 como almacenamiento intermedio (con hasta 12 reintentos en ventana de 2 horas). Luego el pipeline de migración en [src/carflip/storage/migrar_s3_a_r2.py](src/carflip/storage/migrar_s3_a_r2.py):

1. Lista objetos en S3
2. Convierte imágenes a AVIF con Pillow ([src/carflip/scrapers/image_utils.py](src/carflip/scrapers/image_utils.py))
3. Sube a Cloudflare R2 (CDN) con hasta 5 reintentos
4. Verifica existencia antes de resubir

### Logging Estructurado

Cada ejecución de scraper genera logs separados por fase en `logs/{fuente}/run_{YYYYMMDD_HHMMSS}/`:

| Archivo            | Contenido                          |
| ------------------ | ---------------------------------- |
| `todo.log`       | Todos los eventos del ciclo        |
| `ingesta.log`    | Requests HTTP, parsing, fotos      |
| `limpieza.log`   | Deduplicación, normalización     |
| `validacion.log` | Avisos rechazados y razones        |
| `fotos.log`      | Estado de subida de imágenes a S3 |

Implementado en [src/carflip/scrapers/logging_utils.py](src/carflip/scrapers/logging_utils.py).

## Seguridad

### Credenciales

- Todas las credenciales exclusivamente en `.env` — sin keyring, Fernet ni AWS Secrets Manager
- `.env` nunca se commitea al repositorio
- Nunca se loggean passwords, tokens de API ni strings de conexión a BD

### Protección Contra Detección

- User-Agent rotation con `fake-useragent`
- Delays aleatorios entre requests (configurable: `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS`)
- Playwright + stealth para sitios con protecciones JavaScript
- Sin paralelización de requests al mismo dominio

### Integridad de Datos

- SQLAlchemy ORM con parámetros vinculados — nunca concatenación de strings en SQL
- Validación estructural y semántica antes de cada upsert a PostgreSQL

## Docker

Para entorno local sin instalación de PostgreSQL:

```bash
docker-compose up -d
```

Levanta PostgreSQL con la base de datos `carflip` preconfigurada.

## Versionamiento

### Versión Semántica

Formato: `MAJOR.MINOR.PATCH` — Versión actual: `0.1.0`

| Incremento | Cuándo                                             |
| ---------- | --------------------------------------------------- |
| PATCH      | Bug fixes, mejoras de estabilidad                   |
| MINOR      | Nuevos scrapers, comandos CLI, features observables |
| MAJOR      | Breaking changes en CLI o esquema DB incompatible   |

### Branching

```
main                          # Siempre estable y ejecutable
├── feat/nombre-scraper       # Nuevo scraper o funcionalidad
├── fix/descripcion-bug       # Corrección de bug
├── chore/descripcion         # Dependencias, config, refactor
└── db/descripcion-migracion  # Cambios de esquema Alembic
```

### Commits (Conventional Commits)

Formato: `<tipo>(<scope opcional>): <descripción en español>`

```
feat(checkeados): agregar nuevo scraper Checkeados
fix(autocosmos): manejar estructura DOM actualizada
chore: actualizar httpx a 0.28
db: agregar índice en autocosmos_listings(marca, modelo)
```

## Contribución

1. Crear rama de trabajo desde `main`
2. Implementar cambios siguiendo [CLAUDE.md](CLAUDE.md):
   - Type hints en todas las funciones
   - Logging con loguru (nunca `print()`)
   - Tests para funcionalidad nueva
   - Migraciones Alembic para cambios de schema
3. Validar localmente:
   ```bash
   uv sync
   alembic upgrade head
   pytest
   carflip run
   ```
4. Mergear a `main` cuando los tests pasan y el scraper fue probado manualmente

## Documentación

- [CLAUDE.md](CLAUDE.md) — Arquitectura, convenciones, decisiones de diseño y roadmap
- [DEPLOY_EC2.md](DEPLOY_EC2.md) — Instrucciones de despliegue en EC2 con TMUX + APScheduler
- [TESTS_GUIDE.md](TESTS_GUIDE.md) — Guía de testing
- [src/carflip/scrapers/AutoCosmos/README.md](src/carflip/scrapers/AutoCosmos/README.md) — Detalles del scraper Autocosmos
- [src/carflip/scrapers/Yapo/README.md](src/carflip/scrapers/Yapo/README.md) — Detalles del scraper Yapo

## Resolución de Problemas

### PostgreSQL no disponible

```bash
# Windows (si está instalado):
pg_ctl -D "C:\Program Files\PostgreSQL\data" start

# Con Docker:
docker-compose up -d
```

### Intérprete Python no detectado en VS Code

1. `Ctrl+Shift+P` → "Python: Select Interpreter"
2. Seleccionar `.venv\Scripts\python.exe`

### Timeouts en Playwright (Yapo)

Aumentar los delays en `.env`:

```env
MIN_DELAY_SECONDS=3
MAX_DELAY_SECONDS=8
```

---

**CarFlip — Inteligencia de Mercado Automotriz**

Para documentación técnica completa, consulte [CLAUDE.md](CLAUDE.md).
