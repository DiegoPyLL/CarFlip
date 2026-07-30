# CarFlip Web

Frontend Astro SSR para CarFlip — comparador de avisos de autos en Chile.

## Stack

- **Astro 7** (`output: 'server'`) + adaptador `@astrojs/vercel`
- **Tailwind CSS 4** vía plugin de Vite (`@tailwindcss/vite`)
- **Supabase JS** para lecturas de PostgreSQL
- **Sin JavaScript propio en el cliente**: filtros y paginación con formularios GET y enlaces nativos; el único script de cliente es Vercel Analytics (`@vercel/analytics`)

## Requerimientos

- Node 22.12+ (requisito de Astro 7)

## Setup local

```bash
npm install
npm run dev   # → http://localhost:4321
```

El `.env` vive en la raíz del repo (no en `web/`), compartido con el backend
Python — Astro lo lee de ahí vía `envDir: '../'` en `astro.config.mjs`. Las
mismas variables van también en Vercel como variables de servidor:

| Variable | Uso |
|---|---|
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_SERVICE_KEY` | Clave service_role, solo lecturas (pendiente migrar a anon + RLS) |
| `CDN_BASE_URL` | Dominio público de R2 para las imágenes |
| `RESEND_API_KEY` | API key de Resend para el formulario de `/contacto` |
| `CONTACT_EMAIL` | Correo destino de los mensajes de `/contacto` |

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
│   ├── auto/p/[id].astro     # Ficha de aviso (con JSON-LD)
│   ├── como-funciona.astro
│   └── dashboard.astro       # Catálogo y moderación — noindex, fuera del nav y del sitemap
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
