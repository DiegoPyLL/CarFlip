import type { Aviso } from './tipos';

/**
 * URL del detalle de un aviso.
 *
 * Cada fuente tiene su propio espacio de rutas porque las secuencias son
 * independientes por tabla: los avisos de particulares viven bajo `/auto/p/`, y
 * una fuente futura estrenaría su prefijo en vez de competir por el mismo id.
 *
 * `volver` viaja como `?back=` para que el detalle pueda devolver al listado con
 * los filtros puestos.
 */
export function enlaceAviso(aviso: Pick<Aviso, 'id'>, volver?: string): string {
  const ruta = `/auto/p/${aviso.id}`;
  return volver ? `${ruta}?back=${encodeURIComponent(volver)}` : ruta;
}
