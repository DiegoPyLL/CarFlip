/**
 * Las fuentes de avisos y su tabla, en un solo lugar.
 *
 * Estaba duplicado en `avisos.ts`, `mercado.ts`, `estadisticas.ts` y
 * `metricas.ts`; la quinta fuente habría multiplicado esa copia por cinco.
 */

import type { Aviso } from '../tipos';

export const TABLA_POR_FUENTE: Record<Aviso['fuente'], string> = {
  autocosmos: 'autocosmos_listings',
  yapo: 'yapo_listings',
  autosusados: 'autosusados_listings',
  checkeados: 'checkeados_listings',
  particular: 'particulares_listings',
};

export const FUENTES = Object.keys(TABLA_POR_FUENTE) as Aviso['fuente'][];

/**
 * Las cuatro fuentes que llena el pipeline Python. El dashboard de scraping
 * mide corridas, fallas y fotos: un aviso de particular no pasa por ahí y
 * ensuciaría esas métricas.
 */
export const FUENTES_SCRAPEADAS = FUENTES.filter((f) => f !== 'particular');

export function esFuente(valor: string | null | undefined): valor is Aviso['fuente'] {
  return Boolean(valor) && (FUENTES as string[]).includes(valor as string);
}

/**
 * Los avisos de particulares tienen estados (publicado, pausado, vendido); los
 * scrapeados no. Aplicar este filtro es la única diferencia que la quinta
 * fuente introduce en toda la capa de lectura pública.
 */
export function soloPublicados<T>(query: T, fuente: Aviso['fuente']): T {
  return fuente === 'particular' ? (query as { eq(c: string, v: string): T }).eq('estado', 'publicado') : query;
}
