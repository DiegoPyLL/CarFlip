import { supabase } from './client';
import { FUENTES_SCRAPEADAS, TABLA_POR_FUENTE } from './fuentes';
import type {
  CategoriaDeal,
  CorridaScrape,
  MetricasOperacion,
  MetricasVehiculos,
} from '../tipos';

// Este dashboard mide el pipeline de scraping: corridas, fallas y fotos. Un
// aviso de particular no pasa por ahí, así que se queda fuera de sus KPIs.
const FUENTES = FUENTES_SCRAPEADAS;

const MAX_CORRIDAS = 60;
const MAX_FALLAS = 10000;

function parsearCorrida(r: any): CorridaScrape {
  return {
    id: r.id,
    source: r.source,
    started_at: new Date(r.started_at),
    finished_at: r.finished_at ? new Date(r.finished_at) : null,
    duracion_segundos: r.duracion_segundos,
    paginas_procesadas: r.paginas_procesadas,
    avisos_encontrados: r.avisos_encontrados,
    avisos_unicos: r.avisos_unicos,
    avisos_validos: r.avisos_validos,
    avisos_rechazados: r.avisos_rechazados,
    errors: r.errors ?? 0,
  };
}

export async function obtenerMetricasOperacion(): Promise<MetricasOperacion> {
  const [runsRes, failsRes] = await Promise.all([
    supabase
      .from('scrape_runs')
      .select('*')
      .order('started_at', { ascending: false })
      .limit(MAX_CORRIDAS),
    supabase.from('run_fail_logs').select('run_id, etapa').limit(MAX_FALLAS),
  ]);

  const historial = (runsRes.data ?? []).map(parsearCorrida);
  const fallas = (failsRes.data ?? []) as { run_id: number; etapa: string }[];

  // Última corrida por fuente (historial viene ordenado desc)
  const ultimaPorFuente = new Map<string, CorridaScrape>();
  for (const corrida of historial) {
    if (!ultimaPorFuente.has(corrida.source)) ultimaPorFuente.set(corrida.source, corrida);
  }
  const ultimas = [...ultimaPorFuente.values()];

  const porEtapa = new Map<string, number>();
  for (const f of fallas) porEtapa.set(f.etapa, (porEtapa.get(f.etapa) ?? 0) + 1);
  const fallasPorEtapa = [...porEtapa.entries()]
    .map(([etapa, total]) => ({ etapa, total }))
    .sort((a, b) => b.total - a.total);

  const idsUltimas = new Set(ultimas.map((r) => r.id));
  const fotosFallidasUltimoCiclo = fallas.filter(
    (f) => idsUltimas.has(f.run_id) && f.etapa === 'descarga_foto'
  ).length;

  return { ultimas, historial, fallasPorEtapa, fotosFallidasUltimoCiclo };
}

export async function obtenerMetricasVehiculos(): Promise<MetricasVehiculos> {
  const hace24h = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const hace7d = new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString();

  const [totales, nuevos, bajadas, dealsRes] = await Promise.all([
    Promise.all(
      FUENTES.map((f) =>
        supabase.from(TABLA_POR_FUENTE[f]).select('*', { count: 'exact', head: true })
      )
    ),
    Promise.all(
      FUENTES.map((f) =>
        supabase
          .from(TABLA_POR_FUENTE[f])
          .select('*', { count: 'exact', head: true })
          .gte('primera_vez_visto', hace24h)
      )
    ),
    Promise.all(
      FUENTES.map((f) =>
        supabase
          .from(TABLA_POR_FUENTE[f])
          .select('*', { count: 'exact', head: true })
          .lt('delta_pct', 0)
          .gte('ultima_vez_visto', hace7d)
      )
    ),
    supabase.from('deals').select('categoria').eq('activo', true).limit(5000),
  ]);

  const porFuente = FUENTES.map((fuente, i) => ({ fuente, total: totales[i].count ?? 0 }));
  const totalAvisos = porFuente.reduce((acc, f) => acc + f.total, 0);
  const nuevos24h = nuevos.reduce((acc, r) => acc + (r.count ?? 0), 0);
  const bajadas7d = bajadas.reduce((acc, r) => acc + (r.count ?? 0), 0);

  const porCategoria = new Map<CategoriaDeal, number>();
  for (const d of (dealsRes.data ?? []) as { categoria: CategoriaDeal | null }[]) {
    if (!d.categoria) continue;
    porCategoria.set(d.categoria, (porCategoria.get(d.categoria) ?? 0) + 1);
  }
  const dealsPorCategoria = [...porCategoria.entries()]
    .map(([categoria, total]) => ({ categoria, total }))
    .sort((a, b) => b.total - a.total);
  const dealsActivos = dealsPorCategoria.reduce((acc, d) => acc + d.total, 0);

  return { totalAvisos, porFuente, nuevos24h, bajadas7d, dealsActivos, dealsPorCategoria };
}
