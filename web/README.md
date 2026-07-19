# CarFlip Web

Frontend Astro SSR para CarFlip — comparador de avisos de autos en Chile.

## Stack

- **Astro 7** (`output: 'server'`) + adaptador `@astrojs/vercel`
- **Tailwind CSS 4** vía plugin de Vite (`@tailwindcss/vite`)
- **Supabase JS** para lecturas de PostgreSQL
- **0 KB de JavaScript de cliente**: filtros y paginación con formularios GET y enlaces nativos

## Requerimientos

- Node 22.12+ (requisito de Astro 7)

## Setup local

```bash
npm install
npm run dev   # → http://localhost:4321
```

`web/.env` (las mismas 3 en Vercel como variables de servidor):

| Variable | Uso |
|---|---|
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_SERVICE_KEY` | Clave service_role, solo lecturas (pendiente migrar a anon + RLS) |
| `CDN_BASE_URL` | Base de CloudFront para imágenes |

## Estructura

```
src/
├── env.d.ts                  # Tipos de las variables de entorno
├── styles/global.css         # @import "tailwindcss"
├── layouts/Base.astro        # Shell HTML: meta/OG/canonical, header, footer, prop noindex
├── lib/
│   ├── db/                   # Consultas Supabase: avisos, deals, mercado, estadisticas, metricas
│   ├── filtros.ts            # parsearFiltrosUrl() — fuente de verdad de los query params
│   ├── busqueda.ts           # Normalización de búsqueda (trigramas)
│   ├── formato.ts            # formatearPrecio(), formatearKm(), etc.
│   ├── cdn.ts                # Resolución de URLs de imagen vía CDN
│   └── tipos.ts              # Interfaces (Aviso, Deal, FiltrosAviso, …)
├── pages/
│   ├── index.astro           # Avisos con filtros y paginación
│   ├── deals.astro           # Oportunidades con evaluación IA
│   ├── mercado.astro         # Estadísticas de mercado
│   ├── marcas/[marca].astro  # Detalle por marca
│   ├── auto/[id].astro       # Ficha de aviso (con JSON-LD)
│   ├── como-funciona.astro
│   └── dashboard.astro       # Métricas internas — noindex, fuera del nav y del sitemap
└── components/               # Cards, filtros y paginación (.astro puros)
```

## Comandos

```bash
npm run dev       # desarrollo
npm run build     # producción (dist/ + .vercel/output)
npx astro check   # chequeo TypeScript (pedirá instalar @astrojs/check)
```

`npm run preview` no soporta el adaptador Vercel; usar deploy previews.

## Seguridad de dependencias

`package.json` fuerza `path-to-regexp@6.3.0` (parche del ReDoS [GHSA-9wv6-86v2-598j](https://github.com/advisories/GHSA-9wv6-86v2-598j)) dentro de `@vercel/routing-utils` mediante `overrides`, porque `@astrojs/vercel@11` aún arrastra la versión vulnerable. Retirar el override cuando `npm ls path-to-regexp` muestre ≥ 6.3.0 sin necesitarlo.

## Deploy en Vercel

1. Root Directory → `web/`
2. Variables de entorno de servidor: las 3 de la tabla de arriba
