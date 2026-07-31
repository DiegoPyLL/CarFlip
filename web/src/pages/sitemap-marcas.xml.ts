import type { APIRoute } from 'astro';

import { obtenerMarcas, obtenerPaginasDeMarca } from '@lib/db';

export const prerender = false;

// Google acepta 50.000 URLs por sitemap; muy por debajo de eso, este archivo es
// una consulta por marca y conviene partirlo antes por coste que por formato.
const MAXIMO = 5000;

/**
 * `@astrojs/sitemap` solo descubre rutas estáticas, así que la rama /marcas
 * —SSR y dependiente del catálogo— necesita el suyo, igual que las publicaciones.
 * Son estas páginas las que responden a "toyota yaris 2018 precio", de modo que
 * quedar fuera de todo sitemap las dejaba a merced del enlazado interno.
 *
 * Las tres profundidades salen de las mismas funciones que deciden qué páginas
 * existen (`obtenerMarcas`, `obtenerDatosModelo`), así que el sitemap no puede
 * declarar una URL que responda 404 ni omitir una que sí exista.
 */
export const GET: APIRoute = async ({ site, url }) => {
  const origen = (site ?? new URL(url.origin)).origin;

  const marcas = await obtenerMarcas();

  // Una consulta por marca, todas en paralelo: en serie son tantos viajes de ida
  // y vuelta como marcas, y el endpoint tiene 10 s de presupuesto. De cada una
  // salen sus modelos y los años de cada modelo, sin consultas adicionales.
  const porMarca = await Promise.all(marcas.map(({ slug }) => obtenerPaginasDeMarca(slug)));

  const rutas = marcas.flatMap(({ slug }, i) => {
    const marca = encodeURIComponent(slug);
    return [
      `/marcas/${marca}`,
      ...porMarca[i].flatMap(({ slug: modelo, anios }) => {
        const rutaModelo = `/marcas/${marca}/${encodeURIComponent(modelo)}`;
        return [rutaModelo, ...anios.map((anio) => `${rutaModelo}/${anio}`)];
      }),
    ];
  });

  if (rutas.length > MAXIMO) {
    console.warn(`sitemap-marcas: ${rutas.length} URLs, sobre el máximo de ${MAXIMO}. Toca partirlo.`);
  }

  const entradas = rutas
    .slice(0, MAXIMO)
    .map((ruta) => `<url><loc>${origen}${ruta}</loc></url>`)
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
