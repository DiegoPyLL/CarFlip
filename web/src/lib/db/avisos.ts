import { supabase, POR_PAGINA } from './client';
import type { Aviso, FiltrosAviso, PaginaResultado, FiltrosDisponibles } from '../tipos';

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

const TABLA_POR_FUENTE: Record<Aviso['fuente'], string> = {
  autocosmos: 'autocosmos_listings',
  yapo: 'yapo_listings',
  autosusados: 'autosusados_listings',
  checkeados: 'checkeados_listings',
};

const FUENTES = Object.keys(TABLA_POR_FUENTE) as Aviso['fuente'][];

function mapearAviso(row: RawAviso, fuente: Aviso['fuente']): Aviso {
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
  if (filtros.modelo) {
    const q = filtros.modelo.replace(/'/g, "''");
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

  if (filtros.fuente) {
    const fuente = filtros.fuente;
    let q = supabase.from(TABLA_POR_FUENTE[fuente]).select('*', { count: 'exact' });
    q = aplicarFiltros(q, filtros);
    q = aplicarOrden(q, filtros.orden);
    q = q.range(offset, offset + POR_PAGINA - 1);
    const { data, count, error } = await q;
    if (error) throw error;
    const items = (data ?? []).map((r) => mapearAviso(r as RawAviso, fuente));
    const total = count ?? 0;
    return { items, total, pagina, total_paginas: Math.ceil(total / POR_PAGINA), por_pagina: POR_PAGINA };
  }

  // Todas las fuentes: una query por tabla en paralelo, mezcladas y ordenadas en memoria
  const resultados = await Promise.all(
    FUENTES.map((fuente) => {
      let q = supabase.from(TABLA_POR_FUENTE[fuente]).select('*');
      q = aplicarFiltros(q, filtros);
      q = aplicarOrden(q, filtros.orden);
      return q;
    })
  );

  const combined: Aviso[] = [];
  resultados.forEach(({ data, error }, i) => {
    if (error) throw error;
    combined.push(...(data ?? []).map((r) => mapearAviso(r as RawAviso, FUENTES[i])));
  });

  const ordenado = ordenarCombinado(combined, filtros.orden);
  const total = ordenado.length;
  const items = ordenado.slice(offset, offset + POR_PAGINA);
  return { items, total, pagina, total_paginas: Math.ceil(total / POR_PAGINA), por_pagina: POR_PAGINA };
}

export async function obtenerAviso(id: number): Promise<Aviso | null> {
  for (const fuente of FUENTES) {
    const { data } = await supabase.from(TABLA_POR_FUENTE[fuente]).select('*').eq('id', id).maybeSingle();
    if (data) return mapearAviso(data as RawAviso, fuente);
  }
  return null;
}

export async function obtenerFiltrosDisponibles(): Promise<FiltrosDisponibles> {
  const [resMarca, resAnio, resCombustible] = await Promise.all([
    Promise.all(
      FUENTES.map((fuente) => supabase.from(TABLA_POR_FUENTE[fuente]).select('marca').not('marca', 'is', null))
    ),
    Promise.all(
      FUENTES.map((fuente) => supabase.from(TABLA_POR_FUENTE[fuente]).select('anio').not('anio', 'is', null))
    ),
    Promise.all(
      FUENTES.map((fuente) =>
        supabase.from(TABLA_POR_FUENTE[fuente]).select('combustible').not('combustible', 'is', null)
      )
    ),
  ]);

  const marcas = new Set<string>();
  resMarca.forEach(({ data }) => (data ?? []).forEach((r: any) => marcas.add(r.marca)));

  const anios = new Set<number>();
  resAnio.forEach(({ data }) => (data ?? []).forEach((r: any) => anios.add(r.anio)));

  const combustibles = new Set<string>();
  resCombustible.forEach(({ data }) => (data ?? []).forEach((r: any) => combustibles.add(r.combustible)));

  return {
    marcas: [...marcas].sort(),
    anios: [...anios].sort((a, b) => b - a),
    combustibles: [...combustibles].sort(),
  };
}
