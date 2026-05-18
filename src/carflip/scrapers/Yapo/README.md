# CarFlip

Plataforma que agrega avisos de autos en venta desde portales chilenos, normaliza los datos, los persiste en PostgreSQL y detecta oportunidades de compra mediante análisis de historial de precios.

![CarFlip Logo](carflip_logo.png)

## Portales cubiertos

| Portal | Método |
|---|---|
| MercadoLibre | API REST oficial |
| Autocosmos | httpx + BeautifulSoup4 |
| Autosusados | httpx + BeautifulSoup4 |
| Checkeados | httpx + BeautifulSoup4 |
| Económicos | httpx + BeautifulSoup4 |

---

## Requerimientos

- Python 3.12+
- PostgreSQL 12+ con base de datos `carflip` creada
- [uv](https://docs.astral.sh/uv/) como gestor de paquetes

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd carflip

# 2. Instalar dependencias
uv sync

# 3. Crear base de datos
createdb carflip

# 4. Aplicar esquema
alembic upgrade head
```

### Configuración (.env)

Crear un archivo `.env` en la raíz del proyecto:

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/carflip

# MercadoLibre API
MERCADOLIBRE_APP_ID=tu_app_id
MERCADOLIBRE_CLIENT_SECRET=tu_client_secret

# Rate limiting entre requests
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Scheduler
SCRAPE_INTERVAL_HOURS=6

# Detección de deals
DEAL_THRESHOLD_PCT=15.0

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log

# Cloudflare R2 (opcional, para almacenar imágenes)
R2_ACCOUNT_ID=
R2_BUCKET=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
```

---

## Uso

### Ejecutar scrapers una vez

```bash
carflip run
```

Muestra un menú interactivo para seleccionar todos los scrapers o uno específico.

```bash
# Ejecutar un scraper directamente
carflip run --scraper autocosmosCloud
```

### Iniciar scheduler automático

```bash
carflip start
```

Ejecuta un ciclo inmediatamente y luego repite cada `SCRAPE_INTERVAL_HOURS` (default: 6h).

### Consultar estadísticas de mercado

```bash
carflip market <marca> <modelo> <año>
```

```bash
carflip market Toyota Corolla 2020
# Toyota Corolla 2020
#   Promedio:  $9.500.000
#   Mínimo:    $7.800.000
#   Máximo:    $11.200.000
#   Avisos:    34
```

---

## Arquitectura

### Pipeline

```
INGESTA (scraper.scrape())
──────────────────────────
Cada scraper implementa scrape() → list[AvisoAuto]
Output: data/raw/{fuente}_{fecha}/
  ├── avisos.jsonl     — metadata por aviso
  └── fotos/           — imágenes originales

LIMPIEZA
────────
Deduplicación por id_externo
Conversión de imágenes a AVIF

VALIDACIÓN
──────────
Campos estructurales: formato de año, precio > 0, km ≥ 0
Campos semánticos: año entre 1990 y actual, precio entre $500k y $100M CLP

CARGA
─────
FAIL LOGs → audit store (fail_logs.json por ejecución)
Imágenes AVIF → Cloudflare R2 (retry x5, 2 horas máximo)
Metadata JSON → PostgreSQL vía upsert (retry x5, 2 horas máximo)
```

### Patrón de scrapers

Todos los scrapers heredan de `ScraperBase` en [src/carflip/scrapers/base.py](src/carflip/scrapers/base.py). Solo hay que implementar `scrape()`:

```python
class ScraperAutocosmos(ScraperBase):
    fuente = "autocosmos"
    model_class = AutocosmosListing  # tabla destino en PostgreSQL

    async def scrape(self) -> list[AvisoAuto]:
        # 1. Pedir páginas con httpx
        # 2. Parsear con BeautifulSoup4
        # 3. Llamar await self.espera_aleatoria() entre requests
        # 4. Retornar list[AvisoAuto]
        ...
```

`ScraperBase.ejecutar()` gestiona logging, timing, manejo de errores y upsert a PostgreSQL. No sobreescribirlo.

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

### Tablas de base de datos

Cada scraper tiene su propia tabla. Todas comparten las mismas columnas vía `ListingMixin`:

| Tabla | Scraper |
|---|---|
| `autocosmos_listings` | Autocosmos |
| `mercadolibre_listings` | MercadoLibre |
| `autosusados_listings` | Autosusados |
| `checkeados_listings` | Checkeados |
| `economicos_listings` | Económicos |
| `scrape_runs` | Bitácora de ejecuciones |

Columnas principales: `id_externo` (clave de upsert), `precio`, `precio_anterior`, `delta_pct`, `primera_vez_visto`, `ultima_vez_visto`.

---

## Tests

```bash
# Suite completa
pytest

# Test específico con detalle
pytest -x -v tests/test_price_tracker.py
```

Tests de integración que requieren BD usan `carflip_test`. Tests unitarios de scrapers mockean respuestas HTTP con `respx`, no la base de datos.

---

## Desarrollo

### Agregar un nuevo scraper

1. Crear `src/carflip/scrapers/NuevoSitio/nuevositio.py` heredando de `ScraperBase`
2. Crear modelo SQLAlchemy en `src/carflip/database/models.py` usando `ListingMixin`
3. Generar migración: `alembic revision --autogenerate -m "agregar nuevositio_listings"`
4. Revisar y aplicar: `alembic upgrade head`
5. Registrar en `src/carflip/scheduler/runner.py`

### Branching y commits

```
main                        # siempre estable
feat/nombre-scraper         # nuevo scraper o feature
fix/descripcion-bug         # corrección de bug
chore/descripcion           # dependencias, config
db/descripcion-migracion    # cambios de esquema
```

Formato de commits (Conventional Commits):

```
feat(checkeados): agregar scraper Checkeados Chile
fix(autocosmos): manejar cambio en estructura DOM
chore: actualizar httpx a 0.28
db: agregar índice en mercadolibre_listings(marca, modelo)
```

---

## Resolución de problemas

### PostgreSQL no disponible

```bash
# Windows (servicio instalado)
pg_ctl -D "C:\Program Files\PostgreSQL\data" start

# Docker
docker run --name carflip-db -e POSTGRES_PASSWORD=pass -p 5432:5432 -d postgres
createdb -h localhost -U postgres carflip
```

### Intérprete Python no detectado en VS Code

`Ctrl+Shift+P` → "Python: Select Interpreter" → seleccionar `.venv\Scripts\python.exe`

### Migraciones desactualizadas

```bash
alembic current      # ver versión actual aplicada
alembic upgrade head # aplicar todas las pendientes
```

---

Para documentación técnica completa (arquitectura, convenciones, decisiones de diseño), ver [CLAUDE.md](CLAUDE.md).
