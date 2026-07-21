import { supabase } from './client';
import { FUENTES, TABLA_POR_FUENTE, soloPublicados } from './fuentes';
import type { Aviso, Estadisticas } from '../tipos';

const TAMANO_LOTE = 1000;

// Supabase/PostgREST limita cada select a TAMANO_LOTE filas por defecto,
// así que hay que paginar con .range() para traer tablas más grandes.
async function obtenerTodasLasFilas(fuente: Aviso['fuente'], columnas: string): Promise<any[]> {
  const todas: any[] = [];
  let desde = 0;
  while (true) {
    const { data, error } = await soloPublicados(
      supabase.from(TABLA_POR_FUENTE[fuente]).select(columnas),
      fuente,
    ).range(desde, desde + TAMANO_LOTE - 1);
    if (error) throw error;
    todas.push(...(data ?? []));
    if (!data || data.length < TAMANO_LOTE) break;
    desde += TAMANO_LOTE;
  }
  return todas;
}

export async function obtenerEstadisticas(): Promise<Estadisticas> {
  const resultados = await Promise.all(
    FUENTES.map((fuente) => obtenerTodasLasFilas(fuente, 'precio, ultima_vez_visto'))
  );

  const totalesPorFuente: Record<string, number> = {};
  const todosPrecios: number[] = [];
  const todasFechas: Date[] = [];

  FUENTES.forEach((fuente, i) => {
    const stats = resultados[i];
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
    precio_promedio,
    precio_minimo,
    precio_maximo,
    ultima_actualizacion,
  };
}
