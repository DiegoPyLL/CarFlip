import { supabase } from './client';
import { TABLA_POR_FUENTE } from './fuentes';
import type { CategoriaDeal, ConteoEstados, MetricasCatalogo } from '../tipos';

const TABLA = TABLA_POR_FUENTE.particular;

const ESTADOS = ['publicado', 'pausado', 'vendido'] as const;

/** Tope de deals leídos para el desglose por categoría. */
const MAX_DEALS = 5000;

/** Cuenta filas sin traerlas: `head: true` pide solo el Content-Range. */
function contar(construir: (q: any) => any = (q) => q) {
  return construir(supabase.from(TABLA).select('*', { count: 'exact', head: true }));
}

export async function obtenerMetricasCatalogo(): Promise<MetricasCatalogo> {
  const hace24h = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const hace7d = new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString();

  const [porEstadoRes, nuevos24hRes, nuevos7dRes, bajadas7dRes, sinFotoRes, dealsRes] =
    await Promise.all([
      Promise.all(ESTADOS.map((estado) => contar((q) => q.eq('estado', estado)))),
      contar((q) => q.gte('publicado_en', hace24h)),
      contar((q) => q.gte('publicado_en', hace7d)),
      contar((q) => q.lt('delta_pct', 0).gte('actualizado_en', hace7d)),
      contar((q) => q.eq('estado', 'publicado').is('url_imagen', null)),
      supabase.from('deals').select('categoria').eq('activo', true).limit(MAX_DEALS),
    ]);

  const porEstado = Object.fromEntries(
    ESTADOS.map((estado, i) => [estado, porEstadoRes[i].count ?? 0]),
  ) as unknown as ConteoEstados;

  const porCategoria = new Map<CategoriaDeal, number>();
  for (const d of (dealsRes.data ?? []) as { categoria: CategoriaDeal | null }[]) {
    if (!d.categoria) continue;
    porCategoria.set(d.categoria, (porCategoria.get(d.categoria) ?? 0) + 1);
  }
  const dealsPorCategoria = [...porCategoria.entries()]
    .map(([categoria, total]) => ({ categoria, total }))
    .sort((a, b) => b.total - a.total);

  return {
    totalAvisos: ESTADOS.reduce((acc, e) => acc + porEstado[e], 0),
    porEstado,
    nuevos24h: nuevos24hRes.count ?? 0,
    nuevos7d: nuevos7dRes.count ?? 0,
    bajadas7d: bajadas7dRes.count ?? 0,
    sinFoto: sinFotoRes.count ?? 0,
    dealsActivos: dealsPorCategoria.reduce((acc, d) => acc + d.total, 0),
    dealsPorCategoria,
  };
}
