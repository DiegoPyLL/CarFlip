# Scraper Checkeados

Scraper de [checkeados.cl](https://www.checkeados.cl) con el pipeline cloud
completo: INGESTA → LIMPIEZA → VALIDACIÓN → CARGA (vía `ScraperBase.ejecutar()`).

## Particularidad técnica

El listado `/comprar` se renderiza **client-side** contra una API con
autenticación (`api-checkeados-prod.herokuapp.com`, responde 401 sin token).
Sin embargo el scraping no requiere Playwright:

1. El **sitemap oficial** `/api/sitemap_catalog.xml` lista todas las URLs de
   detalle de los avisos publicados.
2. Cada **página de detalle** viene server-side (Next.js SSR) con el JSON
   completo del vehículo embebido en `<script id="__NEXT_DATA__">` en
   `props.pageProps.vehicle`.

El scraper recorre el sitemap y extrae ese JSON por aviso — sin parseo de HTML
de cards ni navegador headless.

| Propiedad | Valor |
|---|---|
| Fuente de URLs | `https://www.checkeados.cl/api/sitemap_catalog.xml` |
| Volumen | Bajo (~20 avisos, automotora única) |
| Anti-bot | Ninguno apreciable; throttle suave entre detalles |
| Herramientas | httpx (sin BS4 — el dato viene en JSON) |

## Mapeo de campos

| Campo AvisoAuto | Origen en el JSON `vehicle` |
|---|---|
| `id_externo` | SHA-256 de la URL de detalle (`/comprar/{marca}~{modelo}~{año}~{hash}`) |
| `titulo` | `brand` + `model` + `version` + `year` |
| `precio` | `price` |
| `marca` / `modelo` | `brand` / `model` (`.title()`) |
| `anio` / `km` | `year` / `kms` |
| `combustible` | `fuel` |
| `transmision` | `transmission` si viene; respaldo: siglas en el título (`normalizar_transmision`) |
| `traccion` | `traction` si viene; respaldo: mención inequívoca en título/descripción |
| `descripcion` | `description` |
| `ubicacion` | `branch.name` (sucursal, ej. "Movicenter") |
| `url_imagen` | `mainImageUrl` (fallback `images[0].url`); reemplazada por URL del CDN R2 tras conversión AVIF |
| `fecha_publicacion` | `publicationDate[:10]` |
| `disponible` | `status == "Publicado"` |

## Uso

```bash
# Limitado a N avisos (recomendado para pruebas)
.venv\Scripts\python src/carflip/scrapers/Checkeados/checkeadosCloud.py 5

# Catálogo completo (~20 avisos, toma segundos)
.venv\Scripts\python src/carflip/scrapers/Checkeados/checkeadosCloud.py
```

**Clase principal:** `ScraperCheckeadosCloud`
**Tabla en PostgreSQL:** `checkeados_listings`
**Código de fuente:** 104
