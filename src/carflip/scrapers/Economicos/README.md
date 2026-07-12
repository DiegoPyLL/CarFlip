# Scraper Económicos

Scraper de [economicos.cl](https://www.economicos.cl) (grupo El Mercurio) con el
pipeline cloud completo: INGESTA → LIMPIEZA → VALIDACIÓN → CARGA
(vía `ScraperBase.ejecutar()`).

| Propiedad | Valor |
|---|---|
| URL listado | `https://www.economicos.cl/todo_chile/vehiculos?pagina=N` |
| Avisos por página | ~40 |
| Volumen | ~500 páginas (~20.000 avisos), ordenados por fecha descendente |
| Anti-bot | Sin protecciones apreciables |
| Herramientas | httpx + BeautifulSoup4 (lxml) |
| Detalle | Se visita por aviso (semáforo de 10) para combustible, km, descripción y marca/modelo/año confiables |

## Límite de páginas por defecto

El sitio completo no cabe en el presupuesto diario de GitHub Actions, así que
`max_paginas` **por defecto es 50** (~2.000 avisos más recientes por run). Como
el listado viene ordenado por fecha descendente, cada run diario captura lo
nuevo y el histórico se acumula en la BD.

## Estructura del listado

Cada aviso es un `div.result`:

- Link + título: `div.col2 a[href] h3` — "Toyota Corolla 2.0 SEG 4X2 CVT AT 5P - 2025"
- Precio: `li.ecn_precio` — "21.390.000"
- Ubicación: `li.cort_txt` — "Temuco | Araucanía"
- Fecha: `time.timeago[datetime]` — "2026-07-12T16:08:00"
- Imagen: `div.delayed-image-load[data-src]` (se elimina `?size=150` para la imagen completa)

La página de detalle aporta la sección `#specs` (`<li><span>Campo:</span> valor`):
Marca, Modelo, Año, Combustible, Región, Fecha Publicación — y `#description p`
con el texto libre, del que se extrae el km (regex `N Kms`).

## Uso

```bash
# Limitado a N páginas (recomendado para pruebas)
.venv\Scripts\python src/carflip/scrapers/Economicos/economicosCloud.py 3

# Default: 50 páginas
.venv\Scripts\python src/carflip/scrapers/Economicos/economicosCloud.py
```

**Clase principal:** `ScraperEconomicosCloud`
**Tabla en PostgreSQL:** `economicos_listings`
**Código de fuente:** 105
