import { FUENTES_SCRAPEADAS } from './db/fuentes';
import type { Aviso } from './tipos';

/** Referencia a un aviso scrapeado: lo mínimo que hace falta para encontrarlo. */
export type RefAviso = { fuente: Aviso['fuente']; id: number };

/**
 * URL del detalle de un aviso.
 *
 * Las secuencias son independientes por tabla, así que el id por sí solo no
 * identifica a nadie: el id 757 existe en las cuatro fuentes scrapeadas. La
 * ruta lleva el par completo (`/auto/yapo-757`) y los particulares mantienen su
 * propio espacio (`/auto/p/757`).
 *
 * `volver` viaja como `?back=` para que el detalle pueda devolver al listado con
 * los filtros puestos.
 */
export function enlaceAviso(aviso: Pick<Aviso, 'id' | 'fuente'>, volver?: string): string {
  const ruta =
    aviso.fuente === 'particular' ? `/auto/p/${aviso.id}` : `/auto/${aviso.fuente}-${aviso.id}`;
  return volver ? `${ruta}?back=${encodeURIComponent(volver)}` : ruta;
}

/**
 * Inversa de `enlaceAviso` para las fuentes scrapeadas: `'yapo-757'` vuelve a
 * ser `{ fuente: 'yapo', id: 757 }`.
 *
 * `particular` no se acepta acá aunque sea una fuente válida: vive en
 * `/auto/p/[id]`. Cualquier otra cosa —incluido el `/auto/757` sin fuente— es
 * `null`, y la ruta responde 404.
 */
export function parsearRefAviso(param: string): RefAviso | null {
  const partes = /^([a-z]+)-(\d+)$/.exec(param);
  if (!partes) return null;

  const fuente = FUENTES_SCRAPEADAS.find((f) => f === partes[1]);
  if (!fuente) return null;

  return { fuente, id: Number(partes[2]) };
}
