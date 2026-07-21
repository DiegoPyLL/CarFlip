import type { Aviso } from './tipos';

/**
 * URL del detalle de un aviso.
 *
 * Los particulares viven en `/auto/p/[id]` y los scrapeados en `/auto/[id]`:
 * las secuencias son independientes por tabla, así que un mismo id puede existir
 * en dos fuentes y una sola ruta no podría distinguirlas.
 *
 * `volver` viaja como `?back=` para que el detalle pueda devolver al listado con
 * los filtros puestos.
 */
export function enlaceAviso(aviso: Pick<Aviso, 'id' | 'fuente'>, volver?: string): string {
  const ruta = aviso.fuente === 'particular' ? `/auto/p/${aviso.id}` : `/auto/${aviso.id}`;
  return volver ? `${ruta}?back=${encodeURIComponent(volver)}` : ruta;
}
