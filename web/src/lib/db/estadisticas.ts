import { supabase } from './client';
import type { Estadisticas } from '../tipos';

export async function obtenerEstadisticas(): Promise<Estadisticas> {
  const [{ data: statsAC }, { data: statsYP }] = await Promise.all([
    supabase.from('autocosmos_listings').select('precio, ultima_vez_visto'),
    supabase.from('yapo_listings').select('precio, ultima_vez_visto'),
  ]);

  const preciosAC = (statsAC ?? []).map((r: any) => r.precio ? parseFloat(r.precio) : null).filter((p): p is number => p !== null);
  const preciosYP = (statsYP ?? []).map((r: any) => r.precio ? parseFloat(r.precio) : null).filter((p): p is number => p !== null);

  const totalAC = statsAC?.length ?? 0;
  const totalYP = statsYP?.length ?? 0;
  const total = totalAC + totalYP;

  const todosPrecios = [...preciosAC, ...preciosYP];
  const precio_promedio = todosPrecios.length > 0 ? todosPrecios.reduce((a, b) => a + b, 0) / todosPrecios.length : null;
  const precio_minimo = todosPrecios.length > 0 ? Math.min(...todosPrecios) : null;
  const precio_maximo = todosPrecios.length > 0 ? Math.max(...todosPrecios) : null;

  const fechasAC = (statsAC ?? []).map((r: any) => r.ultima_vez_visto ? new Date(r.ultima_vez_visto) : null).filter((d): d is Date => d !== null);
  const fechasYP = (statsYP ?? []).map((r: any) => r.ultima_vez_visto ? new Date(r.ultima_vez_visto) : null).filter((d): d is Date => d !== null);
  const todasFechas = [...fechasAC, ...fechasYP];
  const ultima_actualizacion = todasFechas.length > 0 ? new Date(Math.max(...todasFechas.map(d => d.getTime()))) : null;

  return {
    total_avisos: total,
    total_autocosmos: totalAC,
    total_yapo: totalYP,
    precio_promedio,
    precio_minimo,
    precio_maximo,
    ultima_actualizacion,
  };
}
