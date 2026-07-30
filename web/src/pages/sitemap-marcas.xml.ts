import type { APIRoute } from 'astro';

import { obtenerMarcas } from '@lib/db';

export const prerender = false;

// `@astrojs/sitemap` solo descubre rutas estáticas, así que /marcas/{marca} —SSR
// y dependiente del catálogo— necesita el suyo, igual que las publicaciones.
// Son las páginas de marca las que responden a "autos <marca> en Chile", de modo
// que quedar fuera de todo sitemap las dejaba a merced del enlazado interno.
export const GET: APIRoute = async ({ site, url }) => {
  const origen = (site ?? new URL(url.origin)).origin;

  // `obtenerMarcas` es la misma fuente que enlaza el hub /marcas, y ya entrega
  // los slugs en minúsculas y agrupados —la única forma que sirve un 200, el
  // resto redirige—. Compartirla evita que el sitemap liste una URL que el hub
  // no enlaza, o al revés.
  const marcas = await obtenerMarcas();

  const entradas = marcas
    .map(({ slug }) => `<url><loc>${origen}/marcas/${encodeURIComponent(slug)}</loc></url>`)
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
