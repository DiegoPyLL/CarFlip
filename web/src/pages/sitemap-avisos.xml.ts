import type { APIRoute } from 'astro';

import { supabase } from '@lib/db/client';
import { TABLA_AVISOS } from '@lib/publicaciones/consultas';

export const prerender = false;

// `@astrojs/sitemap` solo descubre rutas estáticas, así que las publicaciones
// —que son SSR y cambian a diario— necesitan su propio sitemap. El tope evita
// que un catálogo grande genere una respuesta desmedida; el límite del formato
// son 50.000 URLs, así que hay margen antes de tener que partir el archivo.
// Alcanzarlo se avisa por consola: el problema de truncar no es truncar, es
// hacerlo en silencio.
const MAXIMO = 5000;

export const GET: APIRoute = async ({ site, url }) => {
  const origen = (site ?? new URL(url.origin)).origin;

  const { data, error } = await supabase
    .from(TABLA_AVISOS)
    .select('id,actualizado_en')
    .eq('estado', 'publicado')
    .order('actualizado_en', { ascending: false })
    .limit(MAXIMO);

  if (error) console.error('No se pudo generar el sitemap de avisos:', error.message);

  // Si volvieron exactamente `MAXIMO` filas es que había al menos esa cantidad
  // publicadas, así que las sobrantes quedaron fuera. Toca partir el sitemap en
  // varios archivos y declararlos en un sitemap index.
  if (data && data.length === MAXIMO) {
    console.warn(
      `Sitemap de avisos: se alcanzó el tope de ${MAXIMO} URLs y hay avisos publicados ` +
        'quedando fuera. Toca partirlo en varios archivos con un sitemap index.',
    );
  }

  const entradas = (data ?? [])
    .map(
      ({ id, actualizado_en }) =>
        `<url><loc>${origen}/auto/p/${id}</loc><lastmod>${new Date(actualizado_en).toISOString()}</lastmod></url>`,
    )
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
