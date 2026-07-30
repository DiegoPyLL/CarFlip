import type { APIRoute } from 'astro';

import { obtenerFiltrosDisponibles } from '@lib/db';

export const prerender = false;

// `@astrojs/sitemap` solo descubre rutas estáticas, así que /marcas/{marca} —SSR
// y dependiente del catálogo— necesita el suyo, igual que las publicaciones.
// Son las páginas de marca las que responden a "autos <marca> en Chile", de modo
// que quedar fuera de todo sitemap las dejaba a merced del enlazado interno.
export const GET: APIRoute = async ({ site, url }) => {
  const origen = (site ?? new URL(url.origin)).origin;

  const { marcas } = await obtenerFiltrosDisponibles();

  // En minúsculas y sin repetir: es la única forma que sirve un 200, el resto
  // redirige. `Set` porque el catálogo puede traer "Kia" y "KIA" de dos fuentes.
  const slugs = [...new Set(marcas.map((m) => m.toLowerCase()))].sort();

  const entradas = slugs
    .map((slug) => `<url><loc>${origen}/marcas/${encodeURIComponent(slug)}</loc></url>`)
    .join('');

  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${entradas}</urlset>`,
    {
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
        'Cache-Control': 'public, max-age=3600',
      },
    },
  );
};
