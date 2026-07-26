import { aplicarFiltros } from './avisos';
import { supabase } from './client';
import type { CategoriaDeal, Deal, FiltrosDeal, FiltrosDisponibles, Fuente } from '../tipos';

type RawDeal = {
  id: number;
  fuente: Fuente;
  id_externo: string;
  url: string;
  titulo: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  km: number | null;
  ubicacion: string | null;
  transmision: string | null;
  traccion: string | null;
  precio: string;
  moneda: string;
  url_imagen: string | null;
  precio_mercado: string | null;
  pct_vs_mercado: number | null;
  delta_pct: number | null;
  comparables: number | null;
  categoria: CategoriaDeal | null;
  puntaje: number | null;
  riesgos: string[] | null;
  resumen: string | null;
  categorizado_en: string | null;
  actualizado_en: string | null;
};

function mapearDeal(row: RawDeal): Deal {
  return {
    ...row,
    precio: parseFloat(row.precio),
    precio_mercado: row.precio_mercado !== null ? parseFloat(row.precio_mercado) : null,
    riesgos: Array.isArray(row.riesgos) ? row.riesgos : [],
    categorizado_en: row.categorizado_en ? new Date(row.categorizado_en) : null,
    actualizado_en: row.actualizado_en ? new Date(row.actualizado_en) : null,
  };
}

/**
 * Deals activos de la tabla `deals` (detectados por candidatos.sql y
 * categorizados por IA). Excluye los "descartar"; los aún sin categorizar
 * (categoria null) se incluyen para no ocultar señal.
 *
 * El orden es el del algoritmo —puntaje, luego cuánto está bajo el mercado— y
 * no se puede cambiar desde la URL: la selección es curada, no un listado.
 * `limite` recorta ese ranking, así que lo que vuelve son siempre los mejores N
 * que cumplen los filtros.
 */
export async function obtenerDeals(filtros: FiltrosDeal, limite = 100): Promise<Deal[]> {
  let query = supabase
    .from('deals')
    .select('*')
    .eq('activo', true)
    .or('categoria.is.null,categoria.neq.descartar');

  // Los campos que un deal comparte con un aviso se filtran con el mismo código
  // que el listado; acá solo queda lo que existe únicamente en una selección IA.
  query = aplicarFiltros(query, filtros);
  if (filtros.fuente) query = query.eq('fuente', filtros.fuente);
  if (filtros.categoria) query = query.eq('categoria', filtros.categoria);
  if (filtros.puntaje_min) query = query.gte('puntaje', filtros.puntaje_min);

  query = query
    .order('puntaje', { ascending: false, nullsFirst: false })
    .order('pct_vs_mercado', { ascending: true })
    .limit(limite);

  const { data, error } = await query;
  if (error) throw error;
  return (data ?? []).map((r) => mapearDeal(r as RawDeal));
}

/**
 * Marcas y años presentes en los deals activos, para poblar los selects.
 *
 * Se consulta la tabla `deals` y no las cinco de avisos: ofrecer una marca sin
 * ningún deal solo lleva a una página vacía. Sin filtrar por los filtros
 * activos, para que siempre se pueda ampliar la búsqueda y no solo estrecharla.
 * `combustibles` va vacío: no es columna de `deals`.
 */
export async function obtenerFiltrosDeals(): Promise<FiltrosDisponibles> {
  const { data } = await supabase
    .from('deals')
    .select('marca,anio')
    .eq('activo', true)
    .or('categoria.is.null,categoria.neq.descartar');

  const marcas = new Set<string>();
  const anios = new Set<number>();
  for (const fila of (data ?? []) as { marca: string | null; anio: number | null }[]) {
    if (fila.marca) marcas.add(fila.marca);
    if (fila.anio) anios.add(fila.anio);
  }

  return {
    marcas: [...marcas].sort(),
    anios: [...anios].sort((a, b) => b - a),
    combustibles: [],
  };
}
