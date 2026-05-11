# Autocosmos Scraper

Scraper asincrónico HTTP para [autocosmos.cl](https://www.autocosmos.cl). Obtiene avisos de autos usados con paginación automática y rate limiting.

**Ubicación del módulo:** `src/carflip/scrapers/Autocosmos/`

---

## Instalación de dependencias

### Opción 1: Desde el proyecto principal (recomendado)

```bash
uv sync
```

### Opción 2: Solo este módulo

```bash
pip install -r src/carflip/scrapers/Autocosmos/requirements.txt
# o con uv
uv pip install -r src/carflip/scrapers/Autocosmos/requirements.txt
```

---

## Uso

### Desde Python

```python
import asyncio
from carflip.scrapers.Autocosmos import AutocosmosClient

async def main():
    async with AutocosmosClient() as client:
        # Fetch + descarga imágenes + exporta Markdown automáticamente
        resultados = await client.fetch_todo(max_paginas=5)

    for aviso in resultados["usados"]:
        print(f"{aviso.titulo} — ${aviso.precio} | {aviso.km} km | {aviso.anio}")

asyncio.run(main())
```

### Métodos disponibles

| Método | Descripción |
|---|---|
| `fetch_usados(max_paginas=10)` | Obtiene autos usados con paginación |
| `fetch_todo(max_paginas=10, guardar=True, ruta_destino=None)` | Fetch + exporta a Markdown |
| `guardar_resultados(avisos, ruta_destino=None)` | Descarga imágenes y genera el `.md` |

### Salida generada

Por cada ejecución se crea en `settings.output_dir`:

```
Archivos locales/
├── autocosmos_20260511_143022.md   ← todos los campos de cada aviso
└── imagenes/
    ├── 12345.jpg                   ← imagen descargada por id_externo
    ├── 67890.webp
    └── ...
```

El Markdown incluye **todos los campos** de `AvisoAuto` — los nulos se muestran como `—`.

---

## Configuración

Variables de entorno en `.env`:

```env
MIN_DELAY_SECONDS=2.0   # Delay mínimo entre requests (segundos)
MAX_DELAY_SECONDS=6.0   # Delay máximo entre requests (segundos)
```

---

## Rate limiting

- Delay aleatorio entre cada página: `MIN_DELAY_SECONDS` a `MAX_DELAY_SECONDS`
- User-Agent rotativo en cada request
- No requiere autenticación (avisos públicos)

---

## Estructura de datos

Cada aviso se mapea a `AvisoAuto`:

| Campo | Fuente | Notas |
|---|---|---|
| `fuente` | — | Siempre `"autocosmos"` |
| `id_externo` | URL | Segmento numérico final de la URL |
| `url` | URL | Enlace directo al aviso |
| `titulo` | `<img alt>` | Alt de la imagen de portada |
| `precio` | Texto | Regex sobre `$` en pesos CLP |
| `moneda` | — | Siempre `"CLP"` |
| `marca` | URL | Segmento 4 de la URL (`/auto/usado/{marca}/...`) |
| `modelo` | URL | Segmento 5 de la URL |
| `anio` | Texto | Regex `\b(19\|20)\d{2}\b` |
| `km` | Texto | Regex sobre `N km` |
| `ubicacion` | Texto | Primera parte no numérica separada por `\|` |
| `combustible` | — | No disponible en listado (solo en detalle) |
| `url_imagen` | `<img src>` | Thumbnail de portada |
| `disponible` | — | Siempre `True` (solo se listan activos) |
| `fecha_publicacion` | — | No disponible en listado |

---

## Paginación

Autocosmos usa el parámetro `?pidx=N` para paginación:

```
https://www.autocosmos.cl/auto/usado          ← página 1
https://www.autocosmos.cl/auto/usado?pidx=2   ← página 2
```

El scraper se detiene automáticamente si una página no retorna avisos.

---

## Dependencias

| Paquete | Versión | Propósito |
|---|---|---|
| `httpx` | ≥0.27 | Cliente HTTP asincrónico |
| `beautifulsoup4` | ≥4.12 | Parser HTML |
| `lxml` | ≥5.2 | Backend rápido para BeautifulSoup |
| `fake-useragent` | ≥1.5 | Rotación de User-Agent |
| `loguru` | ≥0.7 | Logging estructurado |

---

## Limitaciones

- Solo scrapea autos **usados** públicos (sin login)
- El campo `combustible` no está disponible en el listado; requeriría visitar cada aviso individual
- Los selectores se basan en la estructura de URL de autocosmos.cl — si el sitio cambia el formato de URL, actualizar `_PATRON_AVISO` en `autocosmos.py`

---

## Archivos del módulo

```
src/carflip/scrapers/Autocosmos/
├── autocosmos.py     ← Cliente HTTP principal
├── __init__.py       ← Exporta AutocosmosClient
├── requirements.txt  ← Dependencias
└── README.md         ← Este archivo
```
