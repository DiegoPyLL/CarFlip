import { supabase } from './client';
import type { CategoriaDeal, Deal, FuenteDeal } from '../tipos';

type RawDeal = {
  id: number;
  fuente: FuenteDeal;
  id_externo: string;
  url: string;
  titulo: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  km: number | null;
  ubicacion: string | null;
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
 */
export async function obtenerDeals(
  fuente?: FuenteDeal,
  categoria?: CategoriaDeal,
  limite = 48
): Promise<Deal[]> {
  let query = supabase
    .from('deals')
    .select('*')
    .eq('activo', true)
    .or('categoria.is.null,categoria.neq.descartar')
    .order('puntaje', { ascending: false, nullsFirst: false })
    .order('pct_vs_mercado', { ascending: true })
    .limit(limite);

  if (fuente) query = query.eq('fuente', fuente);
  if (categoria && categoria !== 'descartar') query = query.eq('categoria', categoria);

  const { data } = await query;
  return (data ?? []).map(r => mapearDeal(r as RawDeal));
}
