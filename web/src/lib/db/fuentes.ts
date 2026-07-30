/**
 * Las fuentes de avisos y su tabla, en un solo lugar.
 *
 * Hoy hay una sola: los avisos que publican los particulares. La indirección se
 * mantiene a propósito —la consumen `avisos.ts`, `mercado.ts`, `estadisticas.ts`
 * y `metricas.ts`— porque el catálogo de una automotora con acuerdo entra como
 * una fuente más, y colapsarla al literal obligaría a rehacer la capa de lectura
 * completa para recuperarla.
 */

import type { Aviso } from '../tipos';

export const TABLA_POR_FUENTE: Record<Aviso['fuente'], string> = {
  particular: 'particulares_listings',
};

export const FUENTES = Object.keys(TABLA_POR_FUENTE) as Aviso['fuente'][];

/**
 * Los avisos tienen estados (publicado, pausado, vendido) y solo los publicados
 * son oferta vigente. Va como función y no inline en cada consulta para que una
 * fuente futura sin estados pueda saltarse el filtro en un solo lugar.
 */
export function soloPublicados<T>(query: T, fuente: Aviso['fuente']): T {
  return fuente === 'particular' ? (query as { eq(c: string, v: string): T }).eq('estado', 'publicado') : query;
}
