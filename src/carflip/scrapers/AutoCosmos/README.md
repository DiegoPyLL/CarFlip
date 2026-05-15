# Autocosmos Scraper

Scraper asincrónico HTTP para [autocosmos.cl](https://www.autocosmos.cl). Obtiene avisos de autos usados con paginación automática y rate limiting.

**Ubicación del módulo:** `src/carflip/scrapers/AutoCosmos/`

---

## Instalación de dependencias

### Opción 1: Desde el proyecto principal (recomendado)

```bash
uv sync
```

### Opción 2: Solo este módulo

```bash
pip install -r src/carflip/scrapers/AutoCosmos/requirements.txt
# o con uv
uv pip install -r src/carflip/scrapers/AutoCosmos/requirements.txt
```

---

## Uso

### Integrado al runner (producción)

El scraper se registra automáticamente y se ejecuta via `carflipper run` o `carflipper start`.
No requiere configuración adicional.

```bash
carflipper run       # ejecuta todos los scrapers una vez
carflipper start     # inicia el scheduler (cada 6h)
```

### Standalone — solo fetch, sin guardar

```python
import asyncio
from carflip.scrapers.AutoCosmos.autocosmos import AutocosmosClient

async def main():
    async with AutocosmosClient() as client:
        avisos = await client.fetch_usados(max_paginas=5)

    for aviso in avisos:
        print(f"{aviso.titulo} — ${aviso.precio} | {aviso.km} km | {aviso.anio}")

asyncio.run(main())
```

### Standalone — fetch + exportar Markdown + descargar imágenes

```python
import asyncio
from carflip.scrapers.AutoCosmos.autocosmos import AutocosmosClient

async def main():
    async with AutocosmosClient() as client:
        resultados = await client.fetch_todo(max_paginas=5, guardar=True)

    print(f"{len(resultados['usados'])} avisos exportados")

asyncio.run(main())
```

> Esta funcionalidad (`fetch_todo`) es una utilidad de desarrollo/exploración. En producción
> el runner usa solo `fetch_usados` + upsert a la BD.

### Desde línea de comandos (script directo)

```bash
# Todas las páginas + upsert a BD
.venv\Scripts\python -m carflip.scrapers.AutoCosmos.autocosmos

# Limitar a N páginas
.venv\Scripts\python -m carflip.scrapers.AutoCosmos.autocosmos 5
```

---

## Métodos disponibles

| Método | Descripción |
|---|---|
| `fetch_usados(max_paginas=None)` | Obtiene todos los avisos usados con paginación. Uso en producción. |
| `fetch_todo(max_paginas=None, guardar=True, ruta_destino=None)` | Fetch + exporta a Markdown con imágenes. Solo para desarrollo/exploración. |

---

## Salida generada por `fetch_todo`

Por cada ejecución se crea en `settings.output_dir`:

```
Archivos locales/
├── autocosmos_marca_modelo_anio_<hash>.md   ← campos de cada aviso
└── imagenes/
    ├── autocosmos_toyota_corolla_2020_<hash>.jpg
    └── ...
```

El Markdown incluye todos los campos de `AvisoAuto` — los nulos se muestran como `—`.

---

## Configuración

Variables de entorno en `.env`:

```env
MIN_DELAY_SECONDS=2.0   # Delay mínimo entre requests (segundos)
MAX_DELAY_SECONDS=6.0   # Delay máximo entre requests (segundos)
OUTPUT_DIR=output        # Directorio de salida para fetch_todo
```

---

## Rate limiting

- Delay aleatorio entre cada página: `MIN_DELAY_SECONDS` a `MAX_DELAY_SECONDS`
- User-Agent rotativo en cada request via `fake-useragent`
- No requiere autenticación (avisos públicos)

---

## Estructura de datos

Cada aviso se mapea a `AvisoAuto`:

| Campo | Fuente | Notas |
|---|---|---|
| `fuente` | — | Siempre `"autocosmos"` |
| `id_externo` | URL | Segmento numérico final de la URL |
| `url` | URL | Enlace directo al aviso |
| `titulo` | `<img alt>` | Alt de la imagen de portada; fallback al texto del card |
| `precio` | Texto del card | Regex sobre `$` en pesos CLP |
| `moneda` | — | Siempre `"CLP"` |
| `marca` | URL | Segmento 4 (`/auto/usado/{marca}/...`) |
| `modelo` | URL | Segmento 5 |
| `anio` | Texto del card | Regex `\b(19\|20)\d{2}\b` |
| `km` | Texto del card | Regex sobre `N km` |
| `ubicacion` | Texto del card | Primera parte no numérica separada por `\|` |
| `combustible` | — | No disponible en listado; requiere visitar el detalle |
| `url_imagen` | `<img src>` o `data-src` | Thumbnail de portada |
| `disponible` | — | Siempre `True` (solo se listan activos) |
| `fecha_publicacion` | — | No disponible en listado |

---

## Paginación

Autocosmos usa el parámetro `?pidx=N`:

```
https://www.autocosmos.cl/auto/usado?pidx=1   ← página 1
https://www.autocosmos.cl/auto/usado?pidx=2   ← página 2
```

El scraper itera hasta que la página no devuelva cards. El parámetro `max_paginas` permite
limitar la cantidad (`None` = sin límite, valor por defecto).

La deduplicación se hace por URL a lo largo de todas las páginas mediante un `set` compartido
entre iteraciones — si el mismo aviso aparece en el sidebar de múltiples páginas, se procesa
una sola vez.

---

## Dependencias

| Paquete | Versión | Propósito |
|---|---|---|
| `httpx` | ≥0.27 | Cliente HTTP asincrónico |
| `beautifulsoup4` | ≥4.12 | Parser HTML |
| `lxml` | ≥5.2 | Backend rápido para BeautifulSoup |
| `fake-useragent` | ≥1.5 | Rotación de User-Agent |
| `loguru` | ≥0.7 | Logging estructurado |
| `pydantic-settings` | ≥2.3 | Lectura de configuración desde `.env` |
| `sqlalchemy[asyncio]` | ≥2.0 | ORM async (necesario para el bloque `__main__`) |
| `asyncpg` | ≥0.29 | Driver PostgreSQL async |

---

## Limitaciones conocidas

- Solo scrapea autos **usados** públicos — no requiere login.
- `combustible`, `descripcion` y `fecha_publicacion` no están disponibles en el listado; requieren visitar el detalle de cada aviso (no implementado).
- La extracción de `marca` y `modelo` se hace desde la URL, no desde el HTML. Si el sitio cambia el formato de URL, actualizar `_PATRON_AVISO` en `autocosmos.py`.
- La extracción de precio, km y año se hace sobre el texto completo del card — si el sitio mueve estos datos fuera del `<a>` de la tarjeta, dejarán de extraerse.
- No hay retry ante errores de red: un error en la página N detiene el scrape desde esa página en adelante.

Ver [TODO.md](TODO.md) para el detalle completo de mejoras pendientes.

---

## Archivos del módulo

```
src/carflip/scrapers/AutoCosmos/
├── autocosmos.py     ← Cliente HTTP y adaptador ScraperBase
├── __init__.py       ← Exporta AutocosmosClient y ScraperAutocosmos
├── requirements.txt  ← Dependencias para uso standalone
├── TODO.md           ← Mejoras pendientes y deuda técnica
└── README.md         ← Este archivo
```
