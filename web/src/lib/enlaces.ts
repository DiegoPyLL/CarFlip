import type { Aviso } from './tipos';

/**
 * URL del detalle de un aviso.
 *
 * Cada fuente tiene su propio espacio de rutas porque las secuencias son
 * independientes por tabla: los avisos de particulares viven bajo `/auto/p/`, y
 * una fuente futura estrenaría su prefijo en vez de competir por el mismo id.
 */
export function enlaceAviso(aviso: Pick<Aviso, 'id'>): string {
  return `/auto/p/${aviso.id}`;
}

/**
 * A dónde vuelve el detalle de un aviso: el listado del que se vino, con sus
 * filtros puestos.
 *
 * Sale del `Referer` y no de un `?back=` en la URL, que es donde vivía. Con el
 * parámetro, cada listado filtrado generaba una URL distinta de la misma ficha
 * —una por tarjeta, veinticuatro por página—: la canónica las consolidaba, pero
 * el rastreo se gastaba igual en recorrerlas todas.
 *
 * Solo se acepta un referente del mismo origen; el resto —una visita desde
 * Google, o un navegador que no manda la cabecera— cae al listado completo.
 */
export function volverAlListado(referente: string | null, origen: string, porDefecto = '/avisos'): string {
  if (!referente) return porDefecto;
  try {
    const url = new URL(referente);
    if (url.origin !== origen) return porDefecto;
    // Sin el hash: el ancla del listado no dice nada sobre a dónde volver.
    return url.pathname + url.search;
  } catch {
    return porDefecto;
  }
}
