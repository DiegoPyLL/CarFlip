# CarFlip — Estado del proyecto y próximos pasos

> Última actualización: 2026-05-24

---

## Qué es CarFlip

Plataforma que agrega avisos de autos en venta desde portales chilenos (Autocosmos y Yapo), normaliza los datos, los persiste en PostgreSQL vía Supabase, y detecta oportunidades de compra mediante historial de precios.

---

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Astro 5 + Tailwind CSS (tema oscuro zinc/amber) |
| Animaciones | Motion.dev (`animate`, `inView`, `stagger`) |
| Base de datos | PostgreSQL via Supabase JS client |
| Deploy | Vercel (SSR con `@astrojs/vercel`) |
| Scrapers | Python + httpx/BS4 (Autocosmos) + Playwright (Yapo) |
| Scheduler | APScheduler cada 6 horas |

---

## Lo que se construyó

### Diseño y tema

- Tema oscuro completo: `bg-zinc-950` base, `zinc-900` cards, `amber-400` acento
- Layout sticky header + nav principal + footer
- Animaciones de entrada con Motion.dev en todas las grids de cards
- Totalmente responsive (mobile → desktop)

### Páginas implementadas

| Ruta | Descripción |
|---|---|
| `/` | Homepage con grid de avisos, filtros avanzados y ordenamiento |
| `/auto/[id]` | Detalle de aviso con specs, imagen y CTA al aviso original |
| `/deals` | Avisos con bajada de precio, ordenados por mayor caída % |
| `/mercado` | Estadísticas globales: marcas, modelos, distribución de precios |
| `/marcas/[marca]` | Página SEO por marca con modelos, años y rangos de precio |
| `/como-funciona` | Proceso, fuentes activas, stats en vivo y FAQ |

### Filtros y búsqueda

- Filtro por **fuente** (Autocosmos / Yapo / Todas) como radio toggles
- Filtro por **marca**, **modelo**, **año**, **combustible**
- Filtro por **km máximo** y **rango de precio**
- **Ordenar por**: más reciente, precio asc/desc, menor km
- **Fuzzy search** con algoritmo Dice de trigramas — "peugot" → "Peugeot"
- El campo modelo busca en `titulo + marca + modelo` simultáneamente

### Arquitectura del frontend

```
web/src/
├── components/
│   ├── avisos/
│   │   ├── CardAviso.astro       ← card de aviso con badge de fuente
│   │   ├── FiltrosBarra.astro    ← filtros superiores (fuente, marca, año)
│   │   ├── FiltrosSidebar.astro  ← filtros avanzados (km, precio, combustible)
│   │   └── Paginacion.astro      ← paginación
│   └── deals/
│       └── CardDeal.astro        ← card con badge verde de bajada %
├── layouts/
│   └── Base.astro                ← shell HTML con nav y footer
├── lib/
│   ├── busqueda.ts               ← fuzzy search con trigramas Dice
│   ├── filtros.ts                ← parseo de params de URL
│   ├── formato.ts                ← formatearPrecio, formatearKm, formatearFecha
│   ├── tipos.ts                  ← interfaces TypeScript
│   └── db/
│       ├── client.ts             ← conexión Supabase
│       ├── avisos.ts             ← obtenerAvisos, obtenerAviso, filtrosDisponibles
│       ├── deals.ts              ← obtenerDeals
│       ├── mercado.ts            ← obtenerDatosMercado, obtenerDatosMarca
│       ├── estadisticas.ts       ← obtenerEstadisticas
│       └── index.ts              ← re-exporta todo
└── pages/
    ├── index.astro
    ├── auto/[id].astro
    ├── deals.astro
    ├── mercado.astro
    ├── marcas/[marca].astro
    └── como-funciona.astro
```

### Commits principales

```
2edc52d  feat(web): páginas de marca y modularización de db
5fad409  feat(web): reestructuración de carpetas
c803089  feat(web): rediseño homepage con tema oscuro y filtros mejorados
84f8804  feat(web): setup design toolchain
```

---

## Fuentes de datos activas

| Portal | Tabla en BD | Estado |
|---|---|---|
| Autocosmos | `autocosmos_listings` | ✅ Activo |
| Yapo | `yapo_listings` | ✅ Activo |
| MercadoLibre | — | 🔜 Próximamente |
| Autosusados | — | 🔜 Próximamente |
| Checkeados | — | 🔜 Próximamente |

---

## Próximos pasos

### Prioridad alta

1. **Agregar MercadoLibre como fuente**
   - Backend: scraper `mercadolibre.py` usando la API oficial
   - Frontend: agregar `'mercadolibre'` al union type de `fuente`, nueva rama en `obtenerAvisos`, opción en el dropdown de fuente, stats en homepage
   - Tabla: `mercadolibre_listings` con migración Alembic

2. **Alertas de deals por WhatsApp o email**
   - Cuando un aviso baja más del umbral configurado (default 5%), notificar
   - Posible integración: Twilio (WhatsApp) o Resend (email)
   - Lógica en el scraper al detectar `delta_pct < -THRESHOLD`

3. **Página de deals mejorada**
   - Filtros por marca y rango de precio dentro de `/deals`
   - Ordenar por: mayor bajada absoluta (en pesos) además de porcentaje
   - Contador de tiempo desde que bajó el precio

### Prioridad media

4. **SEO y meta tags dinámicos**
   - Imagen OG generada dinámicamente para `/marcas/[marca]` con el nombre y estadísticas
   - Sitemap ya está activo via `@astrojs/sitemap`; validar que incluye las rutas `/marcas/*`

5. **Comparador de avisos**
   - Seleccionar 2–3 avisos y compararlos lado a lado (precio, km, año, combustible)
   - Se puede implementar como página `/comparar?ids=1,2,3`

6. **Historial de precios en el detalle**
   - En `/auto/[id]`, mostrar un mini gráfico del historial de precio si hay más de un punto
   - Requiere tabla `precio_historial` en BD o almacenar snapshots en el upsert

### Prioridad baja

7. **Autosusados y Checkeados**
   - Scrapers simples HTTP + BS4, sin Playwright
   - Seguir el checklist de `CLAUDE.md`: backend + frontend en un solo PR

8. **Página `/comparar`**
   - Selección persistida en `localStorage`
   - Tabla comparativa con highlight del mejor valor en cada campo

9. **Tests**
   - Cobertura > 80% en `src/carflip/`
   - Fixtures de HTML estático para testear parsers sin Playwright

10. **Dashboard de admin**
    - Ver logs de scrape, errores por fuente, uptime
    - Podría ser una ruta `/admin` protegida con una variable de entorno simple

---

## Notas de desarrollo

- El `.venv` está en la raíz. Siempre usar `.venv\Scripts\python` como intérprete.
- Variables de entorno en `web/.env`: `SUPABASE_URL` y `SUPABASE_SERVICE_KEY`
- Scrapers corren en EC2 con APScheduler cada 6 horas
- Para agregar una fuente nueva, seguir el checklist en `CLAUDE.md` — backend Y frontend en el mismo PR
