import type { APIRoute } from 'astro';

import { aEntero } from '@lib/campos';
import { obtenerVersiones } from '@lib/db/catalogo';

export const prerender = false;

/**
 * Las versiones de un modelo, para el `<datalist>` del formulario de aviso.
 *
 * Van por aquí y no incrustadas en la página como los modelos: son miles, y
 * servirlas todas para que el usuario use una sería el HTML entero del catálogo
 * en cada carga del formulario.
 *
 * Exige sesión aunque no revele nada privado —es el mismo catálogo público que
 * la página ya muestra— porque solo lo consulta quien está publicando: sin eso
 * es un endpoint que cualquiera puede recorrer entero para copiar el catálogo.
 */
export const GET: APIRoute = async ({ url, locals }) => {
  if (!locals.usuario) return new Response(null, { status: 401 });

  const modeloId = aEntero(url.searchParams.get('modelo'));
  if (modeloId === null || modeloId <= 0) return new Response(null, { status: 400 });

  const versiones = await obtenerVersiones(modeloId);

  return new Response(JSON.stringify(versiones), {
    headers: {
      'Content-Type': 'application/json',
      // El catálogo cambia cuando corre el script de carga, no entre visitas.
      // `private` porque la respuesta depende de haber iniciado sesión.
      'Cache-Control': 'private, max-age=3600',
    },
  });
};
