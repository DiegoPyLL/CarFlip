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
| URL listado | `https://autosusados.cl/autos-usados?pagina=N` |
| Avisos por página | 20 |
| Volumen | ~7.900 avisos (campo `total` del JSON) |
| Anti-bot | **Rate limiting**: el sitio responde `initialPosts={"error": {code: 429}}` si se le pega muy rápido. Los reintentos usan backoff de 20 s |
| Herramientas | httpx (sin BS4 — el dato viene en JSON) |
| Detalle | No se visita: el listado ya trae precio, km, año, combustible, foto y región |

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

# Sin límite (recorre las ~394 páginas del sitio)
.venv\Scripts\python src/carflip/scrapers/Autosusados/autosusadosCloud.py
```

**Clase principal:** `ScraperAutosusadosCloud`
**Tabla en PostgreSQL:** `autosusados_listings`
**Código de fuente:** 103
