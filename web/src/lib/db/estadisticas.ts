import { supabase } from './client';
import type { Aviso, Estadisticas } from '../tipos';

const TABLA_POR_FUENTE: Record<Aviso['fuente'], string> = {
  autocosmos: 'autocosmos_listings',
  yapo: 'yapo_listings',
  autosusados: 'autosusados_listings',
  checkeados: 'checkeados_listings',
  economicos: 'economicos_listings',
};

const FUENTES = Object.keys(TABLA_POR_FUENTE) as Aviso['fuente'][];

export async function obtenerEstadisticas(): Promise<Estadisticas> {
  const resultados = await Promise.all(
    FUENTES.map((fuente) =>
      supabase.from(TABLA_POR_FUENTE[fuente]).select('precio, ultima_vez_visto')
    )
  );

  const totalesPorFuente: Record<string, number> = {};
  const todosPrecios: number[] = [];
  const todasFechas: Date[] = [];

  FUENTES.forEach((fuente, i) => {
    const stats = resultados[i].data ?? [];
    totalesPorFuente[fuente] = stats.length;
    for (const r of stats as any[]) {
      if (r.precio) todosPrecios.push(parseFloat(r.precio));
      if (r.ultima_vez_visto) todasFechas.push(new Date(r.ultima_vez_visto));
    }
  });

  const total = FUENTES.reduce((acc, fuente) => acc + totalesPorFuente[fuente], 0);
  const precio_promedio = todosPrecios.length > 0 ? todosPrecios.reduce((a, b) => a + b, 0) / todosPrecios.length : null;
  const precio_minimo = todosPrecios.length > 0 ? Math.min(...todosPrecios) : null;
  const precio_maximo = todosPrecios.length > 0 ? Math.max(...todosPrecios) : null;
  const ultima_actualizacion = todasFechas.length > 0 ? new Date(Math.max(...todasFechas.map((d) => d.getTime()))) : null;

  return {
    total_avisos: total,
    total_autocosmos: totalesPorFuente.autocosmos,
    total_yapo: totalesPorFuente.yapo,
    total_autosusados: totalesPorFuente.autosusados,
    total_checkeados: totalesPorFuente.checkeados,
    total_economicos: totalesPorFuente.economicos,
    precio_promedio,
    precio_minimo,
    precio_maximo,
    ultima_actualizacion,
  };
}
