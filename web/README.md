# CarFlip Web

Frontend Astro 4 SSR para CarFlip — comparador de avisos de autos en Chile.

## Descripción

Agrega avisos de Autocosmos y MercadoLibre en una sola interfaz. Filtros por fuente, marca, año, combustible y precio. Sin JavaScript de cliente: todos los filtros funcionan con formularios GET nativos.

## Requerimientos

- Node 20+
- Acceso a PostgreSQL con las tablas `autocosmos_listings` y `mercadolibre_listings`

## Setup local

```bash
cp .env.example .env
# Editar .env con tu DATABASE_URL real
npm install
npm run dev
# → http://localhost:4321
```

## Estructura

```
src/
├── env.d.ts                 # Variables de entorno TypeScript
├── layouts/
│   └── Base.astro           # HTML shell con meta, OG, header y footer
├── lib/
│   ├── db.ts                # Conexión postgres.js y funciones de consulta
│   ├── filtros.ts           # parsearFiltrosUrl() — validación de query params
│   ├── formato.ts           # formatearPrecio(), formatearKm(), signosDelta()
│   └── tipos.ts             # Interfaces TypeScript (Aviso, FiltrosAviso, etc.)
├── pages/
│   ├── index.astro          # Grid de listados con filtros y paginación
│   └── auto/
│       └── [id].astro       # Página de detalle con ficha técnica
└── components/
    ├── CardAviso.astro      # Card de aviso (imagen, precio, badge delta)
    ├── FiltrosBarra.astro   # Formulario GET de filtros
    └── Paginacion.astro     # Nav de páginas con ventana deslizante
```

## Filtros disponibles

| Parámetro   | Tipo    | Ejemplo                          |
|-------------|---------|----------------------------------|
| fuente      | string  | `?fuente=autocosmos`             |
| marca       | string  | `?marca=Toyota`                  |
| modelo      | string  | `?modelo=Corolla`                |
| anio        | number  | `?anio=2020`                     |
| precio_min  | number  | `?precio_min=5000000`            |
| precio_max  | number  | `?precio_max=15000000`           |
| km_max      | number  | `?km_max=100000`                 |
| combustible | string  | `?combustible=Bencina`           |
| pagina      | number  | `?pagina=2`                      |

Parámetros inválidos se ignoran silenciosamente.

## Build y preview

```bash
npm run build    # compila para producción (0 errores TypeScript)
npm run preview  # previsualiza el build local
```

## Deploy en Vercel

1. Crear nuevo proyecto en Vercel
2. **Root Directory** → `web/`
3. Variables de entorno (Server):
   - `DATABASE_URL` → URL pooler de PostgreSQL (puerto 6543 para Supabase)
   - `USE_SSL` → `true`

## Decisiones de diseño

- **Sin JS de cliente**: filtros y paginación son formularios GET y `<a>` nativos → 0 bundle JS
- **Paginación de 24 ítems**: equilibrio entre carga y densidad de contenido
- **max: 1 conexión**: evita agotar el límite de conexiones en Supabase free tier
- **UNION ALL**: combina ambas tablas cuando no hay filtro de fuente, con `COUNT(*) OVER()` para evitar segunda query de conteo
