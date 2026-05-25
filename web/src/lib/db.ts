import { createClient } from '@supabase/supabase-js';
import type { Aviso, FiltrosAviso, PaginaResultado, FiltrosDisponibles, Estadisticas } from './tipos';

export interface EstadisticaMarca {
  marca: string;
  total: number;
  precio_promedio: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
}

export interface EstadisticaModelo {
  modelo: string;
  marca: string;
  total: number;
  precio_promedio: number | null;
}

export interface DatosMercado {
  marcas: EstadisticaMarca[];
  modelos: EstadisticaModelo[];
  distribucion: { etiqueta: string; min: number; max: number; total: number }[];
  total: number;
}

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

export async function obtenerDeals(fuente?: 'autocosmos' | 'yapo', limite = 48): Promise<Aviso[]> {
  const THRESHOLD = -5; // bajada de 5% o más

  async function queryTabla(tabla: string, src: 'autocosmos' | 'yapo') {
    const { data } = await supabase
      .from(tabla)
      .select('*')
      .lt('delta_pct', THRESHOLD)
      .not('precio', 'is', null)
      .not('delta_pct', 'is', null)
      .eq('disponible', true)
      .order('delta_pct', { ascending: true })
      .limit(limite);
    return (data ?? []).map(r => mapearAviso(r as RawAviso, src));
  }

  if (fuente === 'autocosmos') return queryTabla('autocosmos_listings', 'autocosmos');
  if (fuente === 'yapo')       return queryTabla('yapo_listings', 'yapo');

  const [ac, yp] = await Promise.all([
    queryTabla('autocosmos_listings', 'autocosmos'),
    queryTabla('yapo_listings', 'yapo'),
  ]);

  return [...ac, ...yp]
    .sort((a, b) => (a.delta_pct ?? 0) - (b.delta_pct ?? 0))
    .slice(0, limite);
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

export async function obtenerDatosMercado(fuente?: 'autocosmos' | 'yapo'): Promise<DatosMercado> {
  type Fila = { marca: string | null; modelo: string | null; precio: string | null };

  async function fetchTabla(tabla: string): Promise<Fila[]> {
    const { data } = await supabase
      .from(tabla)
      .select('marca, modelo, precio')
      .not('marca', 'is', null)
      .limit(10000);
    return (data ?? []) as Fila[];
  }

  let rows: Fila[];
  if (fuente === 'autocosmos') {
    rows = await fetchTabla('autocosmos_listings');
  } else if (fuente === 'yapo') {
    rows = await fetchTabla('yapo_listings');
  } else {
    const [ac, yp] = await Promise.all([
      fetchTabla('autocosmos_listings'),
      fetchTabla('yapo_listings'),
    ]);
    rows = [...ac, ...yp];
  }

  // ── Marcas ──────────────────────────────────────────────────────────
  const marcaMap = new Map<string, { total: number; precios: number[] }>();
  for (const row of rows) {
    if (!row.marca) continue;
    const entry = marcaMap.get(row.marca) ?? { total: 0, precios: [] };
    entry.total++;
    if (row.precio) entry.precios.push(parseFloat(row.precio));
    marcaMap.set(row.marca, entry);
  }

  const marcas: EstadisticaMarca[] = Array.from(marcaMap.entries())
    .map(([marca, { total, precios }]) => ({
      marca,
      total,
      precio_promedio: precios.length ? precios.reduce((a, b) => a + b, 0) / precios.length : null,
      precio_minimo:   precios.length ? Math.min(...precios) : null,
      precio_maximo:   precios.length ? Math.max(...precios) : null,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 20);

  // ── Modelos ─────────────────────────────────────────────────────────
  const modeloMap = new Map<string, { marca: string; total: number; precios: number[] }>();
  for (const row of rows) {
    if (!row.modelo || !row.marca) continue;
    const key = `${row.marca}||${row.modelo}`;
    const entry = modeloMap.get(key) ?? { marca: row.marca, total: 0, precios: [] };
    entry.total++;
    if (row.precio) entry.precios.push(parseFloat(row.precio));
    modeloMap.set(key, entry);
  }

  const modelos: EstadisticaModelo[] = Array.from(modeloMap.entries())
    .map(([key, { marca, total, precios }]) => ({
      modelo: key.split('||')[1],
      marca,
      total,
      precio_promedio: precios.length ? precios.reduce((a, b) => a + b, 0) / precios.length : null,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 15);

  // ── Distribución de precios ─────────────────────────────────────────
  const brackets = [
    { etiqueta: 'Hasta $5M',       min: 0,          max: 5_000_000 },
    { etiqueta: '$5M — $10M',       min: 5_000_000,  max: 10_000_000 },
    { etiqueta: '$10M — $20M',      min: 10_000_000, max: 20_000_000 },
    { etiqueta: '$20M — $35M',      min: 20_000_000, max: 35_000_000 },
    { etiqueta: 'Más de $35M',      min: 35_000_000, max: Infinity },
  ];

  const distribucion = brackets.map(b => ({
    ...b,
    total: rows.filter(r => {
      const p = r.precio ? parseFloat(r.precio) : null;
      return p !== null && p >= b.min && p < b.max;
    }).length,
  }));

  return { marcas, modelos, distribucion, total: rows.length };
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
