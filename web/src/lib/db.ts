import { createClient } from '@supabase/supabase-js';
import type { Aviso, FiltrosAviso, PaginaResultado, FiltrosDisponibles, Estadisticas } from './tipos';

const supabaseUrl = (import.meta.env.SUPABASE_URL as string) || (process.env.SUPABASE_URL as string);
const supabaseKey = (import.meta.env.SUPABASE_SERVICE_KEY as string) || (process.env.SUPABASE_SERVICE_KEY as string);

if (!supabaseUrl || !supabaseKey) {
  throw new Error('SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar definidas en web/.env');
}

const supabase = createClient(supabaseUrl, supabaseKey);

const POR_PAGINA = 24;

type RawAviso = {
  id: number;
  id_externo: string;
  url: string;
  titulo: string;
  precio: string | null;
  moneda: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  km: number | null;
  ubicacion: string | null;
  combustible: string | null;
  descripcion: string | null;
  url_imagen: string | null;
  disponible: boolean | null;
  precio_anterior: string | null;
  delta_pct: number | null;
  primera_vez_visto: string | null;
  ultima_vez_visto: string | null;
};

function mapearAviso(row: RawAviso, fuente: 'autocosmos' | 'yapo'): Aviso {
  return {
    ...row,
    fuente,
    precio: row.precio !== null ? parseFloat(row.precio) : null,
    precio_anterior: row.precio_anterior !== null ? parseFloat(row.precio_anterior) : null,
    primera_vez_visto: row.primera_vez_visto ? new Date(row.primera_vez_visto) : null,
    ultima_vez_visto: row.ultima_vez_visto ? new Date(row.ultima_vez_visto) : null,
  } as unknown as Aviso;
}

function aplicarFiltros(query: any, filtros: FiltrosAviso) {
  if (filtros.marca)      query = query.ilike('marca', `%${filtros.marca}%`);
  // "modelo" busca en titulo + marca + modelo para que "jeep", "grand cherokee", etc. funcionen
  if (filtros.modelo) {
    const q = filtros.modelo.replace(/'/g, "''"); // escape básico de comilla simple
    query = query.or(`titulo.ilike.%${q}%,marca.ilike.%${q}%,modelo.ilike.%${q}%`);
  }
  if (filtros.anio)       query = query.eq('anio', filtros.anio);
  if (filtros.precio_min) query = query.gte('precio', filtros.precio_min);
  if (filtros.precio_max) query = query.lte('precio', filtros.precio_max);
  if (filtros.km_max)     query = query.lte('km', filtros.km_max);
  if (filtros.combustible) query = query.ilike('combustible', `%${filtros.combustible}%`);
  return query;
}

function aplicarOrden(query: any, orden?: string) {
  switch (orden) {
    case 'precio_asc':  return query.order('precio',           { ascending: true,  nullsFirst: false });
    case 'precio_desc': return query.order('precio',           { ascending: false, nullsFirst: false });
    case 'km_asc':      return query.order('km',               { ascending: true,  nullsFirst: false });
    default:            return query.order('ultima_vez_visto', { ascending: false, nullsFirst: false });
  }
}

function ordenarCombinado(items: Aviso[], orden?: string): Aviso[] {
  return items.sort((a, b) => {
    switch (orden) {
      case 'precio_asc':  return (a.precio ?? Infinity) - (b.precio ?? Infinity);
      case 'precio_desc': return (b.precio ?? -Infinity) - (a.precio ?? -Infinity);
      case 'km_asc':      return (a.km ?? Infinity) - (b.km ?? Infinity);
      default: {
        const aT = a.ultima_vez_visto ? new Date(a.ultima_vez_visto).getTime() : 0;
        const bT = b.ultima_vez_visto ? new Date(b.ultima_vez_visto).getTime() : 0;
        return bT - aT;
      }
    }
  });
}

export async function obtenerAvisos(filtros: FiltrosAviso): Promise<PaginaResultado<Aviso>> {
  const pagina = filtros.pagina ?? 1;
  const offset = (pagina - 1) * POR_PAGINA;

  if (filtros.fuente === 'autocosmos') {
    let q = supabase.from('autocosmos_listings').select('*', { count: 'exact' });
    q = aplicarFiltros(q, filtros);
    q = aplicarOrden(q, filtros.orden);
    q = q.range(offset, offset + POR_PAGINA - 1);
    const { data, count, error } = await q;
    if (error) throw error;
    const items = (data ?? []).map(r => mapearAviso(r as RawAviso, 'autocosmos'));
    const total = count ?? 0;
    return { items, total, pagina, total_paginas: Math.ceil(total / POR_PAGINA), por_pagina: POR_PAGINA };
  }

  if (filtros.fuente === 'yapo') {
    let q = supabase.from('yapo_listings').select('*', { count: 'exact' });
    q = aplicarFiltros(q, filtros);
    q = aplicarOrden(q, filtros.orden);
    q = q.range(offset, offset + POR_PAGINA - 1);
    const { data, count, error } = await q;
    if (error) throw error;
    const items = (data ?? []).map(r => mapearAviso(r as RawAviso, 'yapo'));
    const total = count ?? 0;
    return { items, total, pagina, total_paginas: Math.ceil(total / POR_PAGINA), por_pagina: POR_PAGINA };
  }

  // Todas las fuentes: combinar ambas tablas
  let qAC = supabase.from('autocosmos_listings').select('*');
  let qYP = supabase.from('yapo_listings').select('*');
  qAC = aplicarFiltros(qAC, filtros);
  qYP = aplicarFiltros(qYP, filtros);
  qAC = aplicarOrden(qAC, filtros.orden);
  qYP = aplicarOrden(qYP, filtros.orden);

  const [{ data: dataAC, error: errAC }, { data: dataYP, error: errYP }] = await Promise.all([qAC, qYP]);
  if (errAC) throw errAC;
  if (errYP) throw errYP;

  const combined = ordenarCombinado([
    ...(dataAC ?? []).map(r => mapearAviso(r as RawAviso, 'autocosmos')),
    ...(dataYP ?? []).map(r => mapearAviso(r as RawAviso, 'yapo')),
  ], filtros.orden);

  const total = combined.length;
  const items = combined.slice(offset, offset + POR_PAGINA);
  return { items, total, pagina, total_paginas: Math.ceil(total / POR_PAGINA), por_pagina: POR_PAGINA };
}

export async function obtenerAviso(id: number): Promise<Aviso | null> {
  const { data: acRow } = await supabase.from('autocosmos_listings').select('*').eq('id', id).maybeSingle();
  if (acRow) return mapearAviso(acRow as RawAviso, 'autocosmos');

  const { data: yapoRow } = await supabase.from('yapo_listings').select('*').eq('id', id).maybeSingle();
  return yapoRow ? mapearAviso(yapoRow as RawAviso, 'yapo') : null;
}

export async function obtenerFiltrosDisponibles(): Promise<FiltrosDisponibles> {
  const [
    { data: marcasAC }, { data: marcasYP },
    { data: aniosAC },  { data: aniosYP },
    { data: combsAC },  { data: combsYP },
  ] = await Promise.all([
    supabase.from('autocosmos_listings').select('marca').not('marca', 'is', null),
    supabase.from('yapo_listings').select('marca').not('marca', 'is', null),
    supabase.from('autocosmos_listings').select('anio').not('anio', 'is', null),
    supabase.from('yapo_listings').select('anio').not('anio', 'is', null),
    supabase.from('autocosmos_listings').select('combustible').not('combustible', 'is', null),
    supabase.from('yapo_listings').select('combustible').not('combustible', 'is', null),
  ]);

  const marcas = [...new Set([
    ...(marcasAC ?? []).map((r: any) => r.marca as string),
    ...(marcasYP ?? []).map((r: any) => r.marca as string),
  ])].sort();

  const anios = [...new Set([
    ...(aniosAC ?? []).map((r: any) => r.anio as number),
    ...(aniosYP ?? []).map((r: any) => r.anio as number),
  ])].sort((a, b) => b - a);

  const combustibles = [...new Set([
    ...(combsAC ?? []).map((r: any) => r.combustible as string),
    ...(combsYP ?? []).map((r: any) => r.combustible as string),
  ])].sort();

  return { marcas, anios, combustibles };
}

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
