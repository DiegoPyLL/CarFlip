# Autocosmos Scraper — Cloud Pipeline

Scraper asincrónico HTTP para [autocosmos.cl](https://www.autocosmos.cl) con pipeline cloud completo.
Cubre las cuatro etapas del pipeline CarFlip dentro de un solo `scrape()`:

```
INGESTA → LIMPIEZA → VALIDACIÓN → retorno para CARGA
```

**Módulo principal:** `src/carflip/scrapers/AutoCosmos/autocosmosCloud.py`
**Clase:** `ScraperAutocosmosCloud`

---

## Uso

### Integrado al runner (producción)

El scraper se registra en `runner.py` y se ejecuta vía los comandos CLI del proyecto.

```bash
carflip run      # ejecuta todos los scrapers una vez
carflip start    # inicia el scheduler (cada 6h)
```

### Standalone desde línea de comandos

```bash
# 2 páginas (por defecto)
.venv\Scripts\python src/carflip/scrapers/AutoCosmos/autocosmosCloud.py

# N páginas
.venv\Scripts\python src/carflip/scrapers/AutoCosmos/autocosmosCloud.py 5
```

### Standalone desde Python

```python
import asyncio
from carflip.scrapers.AutoCosmos.autocosmosCloud import ScraperAutocosmosCloud
from carflip.database.session import AsyncSessionLocal

async def main():
    scraper = ScraperAutocosmosCloud(max_paginas=3, guardar_raw=True)
    async with AsyncSessionLocal() as sesion:
        resultado = await scraper.ejecutar(sesion)
    print(f"{len(resultado.avisos)} avisos, {resultado.errores} errores")

asyncio.run(main())
```

---

## Pipeline interno de `scrape()`

### 1. Ingesta

- Paginación HTTP sobre `https://www.autocosmos.cl/auto/usado?pidx=N`
- Parseo de cards `<a href="/auto/usado/...">` con BeautifulSoup + lxml
- Deduplicación de hrefs durante la paginación (un aviso no se procesa dos veces aunque aparezca en múltiples páginas)
- Por página: guarda `pagina_NNN.json` en `data/raw/autocosmos_{fecha}/` y descarga imágenes en `fotos/`
- User-Agent rotativo vía `fake-useragent`

### 2. Limpieza

- Deduplicación por `id_externo` sobre el batch completo; los duplicados van a FAIL LOG con `etapa="dedup_json"`

### 3. Validación

Validación estructural:
- `anio`: entero de 4 dígitos
- `precio`: > 0
- `km`: ≥ 0
- `fecha_publicacion`: formato `YYYY-MM-DD`, no puede ser futura

Validación semántica:
- `anio`: entre 1970 y año actual
- `precio`: entre $500.000 y $250.000.000 CLP

Advertencia no bloqueante:
- `km > 100.000` en autos de 2022 en adelante → `logger.warning`, el aviso igual pasa

Los avisos que no superan la validación van a FAIL LOG con `etapa="validacion_json"`.

### 4. FAIL LOG

Al final del scrape, todos los registros de fallo se consolidan en `fail_logs.json` dentro de la carpeta del run:

```json
[
  {
    "timestamp": "2026-05-16T12:00:00+00:00",
    "etapa": "validacion_json",
    "motivo": "precio 300000 fuera de rango [500.000, 100.000.000] CLP",
    "id_externo": "12345678",
    "fuente": "autocosmos"
  }
]
```

Etapas posibles: `dedup_fotos`, `dedup_json`, `validacion_json`.

### 5. Carga

`scrape()` retorna `list[AvisoAuto]` con los avisos válidos. La carga a PostgreSQL la delega `ScraperBase.ejecutar()` vía `uploader.upsert_avisos()`.

La subida a S3/R2 está declarada en `_cargar_a_s3_con_retry()` pero **pendiente de implementar** (lanza `NotImplementedError`).

---

## Estructura de datos

Cada aviso se mapea a `AvisoAuto`:

| Campo | Fuente | Notas |
|---|---|---|
| `fuente` | — | Siempre `"autocosmos"` |
| `id_externo` | URL | Segmento numérico final: `/auto/usado/{marca}/{modelo}/{anio}/{id}` |
| `url` | URL | Enlace directo al aviso |
| `titulo` | `<img alt>` | Alt de la imagen; fallback al texto completo del card (200 chars) |
| `precio` | Texto del card | Regex sobre `$N.NNN` en CLP |
| `moneda` | — | Siempre `"CLP"` |
| `marca` | URL | Segmento 4 del path, title-cased |
| `modelo` | URL | Segmento 5 del path, title-cased |
| `anio` | Texto del card | Regex `\b(19\|20)\d{2}\b` |
| `km` | Texto del card | Regex sobre `N km` |
| `ubicacion` | Texto del card | Primera parte no numérica separada por `\|` |
| `combustible` | — | No disponible en el listado |
| `descripcion` | — | No disponible en el listado |
| `url_imagen` | `<img src>` o `data-src` | Thumbnail de portada |
| `disponible` | — | Siempre `True` |
| `fecha_publicacion` | — | No disponible en el listado |

---

## Raw data generado

Con `guardar_raw=True` (por defecto) se crea en `settings.output_dir`:

```
data/raw/
└── autocosmos_20260516_120000/
    ├── pagina_001.json
    ├── pagina_002.json
    ├── ...
    ├── fail_logs.json
    └── fotos/
        ├── 12345678.jpg
        └── ...
```

Con `guardar_raw=False` el scrape sigue funcionando pero no persiste nada en disco.

---

## Parámetros del constructor

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `max_paginas` | `int \| None` | `None` | Límite de páginas. `None` = sin límite (hasta que no haya más cards) |
| `guardar_raw` | `bool` | `True` | Si guarda JSON y fotos en `data/raw/` |

---

## Configuración (`.env`)

```env
MIN_DELAY_SECONDS=2.0   # Delay mínimo entre páginas
MAX_DELAY_SECONDS=6.0   # Delay máximo entre páginas
OUTPUT_DIR=data/raw     # Directorio de salida para raw data
```

---

## Dependencias

| Paquete | Versión | Propósito |
|---|---|---|
| `httpx` | ≥0.27 | Cliente HTTP asincrónico |
| `beautifulsoup4` | ≥4.12 | Parser HTML |
| `lxml` | ≥5.2 | Backend rápido para BeautifulSoup |
| `fake-useragent` | ≥1.5 | Rotación de User-Agent |
| `loguru` | ≥0.7 | Logging estructurado |
| `pydantic-settings` | ≥2.3 | Lectura de `.env` |
| `sqlalchemy[asyncio]` | ≥2.0 | ORM async |
| `asyncpg` | ≥0.29 | Driver PostgreSQL async |

Instalar con `uv sync` desde la raíz del proyecto.

---

## Limitaciones conocidas

- Solo scrapea la sección de autos **usados** públicos.
- `combustible`, `descripcion` y `fecha_publicacion` no están disponibles en el listado; requieren visitar el detalle de cada aviso (no implementado).
- `marca` y `modelo` se extraen de la URL — si el sitio cambia el formato de path, actualizar `_PATRON_AVISO`.
- La subida a S3/R2 (`_cargar_a_s3_con_retry`) está pendiente de implementar.
- Un error de red en la página N detiene el scrape desde esa página en adelante (no hay retry por página).

---

## Archivos del módulo

```
src/carflip/scrapers/AutoCosmos/
├── autocosmosCloud.py  ← Pipeline cloud completo (este módulo)
├── autocosmos.py       ← Implementación anterior (a eliminar en Fase 1)
├── __init__.py
├── requirements.txt    ← Dependencias para uso standalone
└── README.md           ← Este archivo
```
