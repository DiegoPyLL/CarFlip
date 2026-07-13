# Scraper AutosUsados

Scraper de [autosusados.cl](https://autosusados.cl) con el pipeline cloud completo:
INGESTA → LIMPIEZA → VALIDACIÓN → CARGA (vía `ScraperBase.ejecutar()`).

## Particularidad técnica

El sitio es **Next.js**: cada página de listado embebe los avisos como JSON
estructurado dentro de `<script id="__NEXT_DATA__">` en
`props.pageProps.initialPosts`. El scraper **no parsea HTML de cards** — extrae
ese JSON directamente, lo que lo hace mucho más robusto ante cambios de diseño.

| Propiedad | Valor |
|---|---|
| URL listado | `https://autosusados.cl/autos-usados?page=N` |
| Avisos por página | 20 |
| Volumen | Variable (campo `total` del JSON); tope de seguridad de `_MAX_PAGINAS_ABSOLUTO = 120` páginas |
| Anti-bot | **Rate limiting**: el sitio responde `initialPosts={"error": {code: 429}}` si se le pega muy rápido. Los reintentos usan backoff de 20 s + jitter |
| Herramientas | httpx (sin BS4 — el dato viene en JSON) |
| Detalle | No se visita: el listado ya trae precio, km, año, combustible, foto y región |

### Tope de seguridad de 120 páginas

El catálogo real ronda las ~97 páginas, pero el volumen fluctúa. Un 429
transitorio en una página posterior al fin real del catálogo podía enmascarar
la señal de "sin avisos nuevos" (la respuesta vacía se trataba como posible
caché obsoleta y no cortaba la paginación), haciendo que el scraper siguiera
pidiendo páginas indefinidamente — se observó llegar a la página 130. Se
corrigió esa condición (una lista `posts` vacía siempre corta la paginación,
haya habido rate limit o no) y además se agregó `_MAX_PAGINAS_ABSOLUTO = 120`
como tope duro independiente de `max_paginas` y de `paginas_sitio`.

### El parámetro de paginación es `page`, no `pagina`

El servidor **ignora silenciosamente** cualquier nombre de parámetro que no sea
`page`: devuelve la página 1 con status 200, sin error. Como todos sus avisos ya
fueron vistos, la guardia de "sin avisos nuevos" interpreta eso como fin de
catálogo y corta la paginación en el primer lote — el scraper termina con 20
avisos en vez de ~7.900, sin que nada falle visiblemente.

En el navegador el listado carga por scroll infinito, que llama a
`{NEXT_PUBLIC_API_URL}/v2/cars?catId=N&actualPage=N`. Esa API exige un token
Firebase AppCheck generado en el cliente (responde `401 Invalid Token` sin él),
así que **no se usa**: el SSR con `?page=N` entrega exactamente los mismos avisos
en `__NEXT_DATA__` y no requiere autenticación.

## Mapeo de campos

| Campo AvisoAuto | Origen en el JSON |
|---|---|
| `id_externo` | SHA-256 de la URL de detalle construida |
| `url` | `/{categoria}/{MARCA}/{MODELO}/{table}/{carID}` (categoría desde `categoryID`: 1=autos, 2=camionetas, 3=suv) |
| `titulo` / `descripcion` | `description` (ej. "OPEL GRANDLAND 1.5 GS LINE DIESEL 4X2 AT8 5P") |
| `precio` | `price` |
| `marca` / `modelo` | `brandName` / `modelName` (`.title()`) |
| `anio` | `year` |
| `km` | `kilometers` |
| `combustible` | `fuelName` |
| `ubicacion` | `region` (número oficial de región de Chile → nombre) |
| `url_imagen` | `photo` (reemplazada por URL del CDN R2 tras conversión AVIF) |
| `fecha_publicacion` | No disponible en el listado → `None` |

## Uso

```bash
# Limitado a N páginas (recomendado para pruebas)
.venv\Scripts\python src/carflip/scrapers/Autosusados/autosusadosCloud.py 3

# Sin límite explícito (recorre el catálogo hasta el tope de seguridad de 120 páginas)
.venv\Scripts\python src/carflip/scrapers/Autosusados/autosusadosCloud.py
```

**Clase principal:** `ScraperAutosusadosCloud`
**Tabla en PostgreSQL:** `autosusados_listings`
**Código de fuente:** 103
