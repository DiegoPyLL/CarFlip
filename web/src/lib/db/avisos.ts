import { supabase, POR_PAGINA } from './client';
import { FUENTES, TABLA_POR_FUENTE, soloPublicados } from './fuentes';
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
  transmision: string | null;
  traccion: string | null;
  descripcion: string | null;
  url_imagen: string | null;
  disponible: boolean | null;
  precio_anterior: string | null;
  delta_pct: number | null;
  primera_vez_visto: string | null;
  ultima_vez_visto: string | null;
};

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

/**
 * Query base de una fuente, ya con el filtro de estado que piden los
 * particulares. Devuelve `any` igual que el resto de los constructores de este
 * módulo: con la columna en una variable, supabase-js no puede inferir la fila.
 */
function desde(fuente: Aviso['fuente'], columnas: string, opciones?: { count: 'exact' }): any {
  return soloPublicados(supabase.from(TABLA_POR_FUENTE[fuente]).select(columnas, opciones), fuente);
}

/**
 * Escapa un valor para meterlo dentro de un `or()` de PostgREST.
 *
 * Ahí la coma, el punto y los paréntesis son **gramática**: sin comillas, un
 * `?modelo=zzz,anio.gte.1900` se parsea como un término más del `or()` y el
 * visitante termina filtrando por columnas que no eligió (o rompiendo la consulta
 * con un 400). Entre comillas dobles el texto viaja como valor, y dentro de ellas
 * `"` y `\` se escapan con barra invertida. Los `%` del `ilike` van fuera de la
 * parte escapable pero dentro de las comillas, que es donde PostgREST los espera.
 */
function valorOr(texto: string): string {
  return `"${texto.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
}

/**
 * Traduce `FiltrosAviso` a cláusulas de PostgREST. Lo usan el listado y deals,
 * que comparten estas columnas, así que un filtro nuevo se agrega una sola vez.
 */
export function aplicarFiltros(query: any, filtros: FiltrosAviso) {
  if (filtros.marca)      query = query.ilike('marca', `%${filtros.marca}%`);
  if (filtros.modelo) {
    // Los filtros de una sola columna codifican su valor solos; este es el único
    // que arma una expresión, así que es el único que necesita escapar.
    const q = valorOr(`%${filtros.modelo}%`);
    query = query.or(`titulo.ilike.${q},marca.ilike.${q},modelo.ilike.${q}`);
  }
  if (filtros.anio)       query = query.eq('anio', filtros.anio);
  if (filtros.precio_min) query = query.gte('precio', filtros.precio_min);
  if (filtros.precio_max) query = query.lte('precio', filtros.precio_max);
  if (filtros.km_max)     query = query.lte('km', filtros.km_max);
  if (filtros.combustible) query = query.ilike('combustible', `%${filtros.combustible}%`);
  // `ubicacion` es texto libre ("Comuna, Región"), así que la región se busca
  // dentro del texto en vez de por igualdad. Transmisión y tracción sí se
  // guardan canónicas, así que van por `eq`.
  if (filtros.region)      query = query.ilike('ubicacion', `%${filtros.region}%`);
  if (filtros.transmision) query = query.eq('transmision', filtros.transmision);
  if (filtros.traccion)    query = query.eq('traccion', filtros.traccion);
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

/**
 * Una página del listado.
 *
 * Con una sola fuente el orden y el recorte los hace Postgres (`.range()`), que
 * trae solo las filas de la página en vez de todo el catálogo. Cuando entre una
 * segunda fuente habrá que volver a mezclar en memoria, o mover el listado a una
 * vista que una las tablas en la base y dejar esta función intacta.
 */
export async function obtenerAvisos(filtros: FiltrosAviso): Promise<PaginaResultado<Aviso>> {
  const pagina = filtros.pagina ?? 1;
  const offset = (pagina - 1) * POR_PAGINA;
  const [fuente] = FUENTES;

  let q = desde(fuente, '*', { count: 'exact' });
  q = aplicarFiltros(q, filtros);
  q = aplicarOrden(q, filtros.orden);
  q = q.range(offset, offset + POR_PAGINA - 1);

  const { data, count, error } = await q;
  if (error) throw error;

  const items = (data ?? []).map((r: RawAviso) => mapearAviso(r, fuente));
  const total = count ?? 0;
  return { items, total, pagina, total_paginas: Math.ceil(total / POR_PAGINA), por_pagina: POR_PAGINA };
}

/**
 * Los últimos avisos de un modelo concreto, para su página.
 *
 * Va por coincidencia exacta —las grafías con que el catálogo escribe ese modelo,
 * que resuelve `paginasModelo`— y no por el `or()` difuso de `aplicarFiltros`,
 * que busca el término también en el título: un "Yaris" nombrado en el aviso de
 * otro auto no pertenece a la página del Yaris.
 */
export async function obtenerAvisosModelo(
  marca: string,
  modelos: string[],
  anio?: number,
  limite = 12,
): Promise<Aviso[]> {
  const [fuente] = FUENTES;

  let q = desde(fuente, '*').ilike('marca', marca).in('modelo', modelos);
  if (anio !== undefined) q = q.eq('anio', anio);

  const { data, error } = await aplicarOrden(q).limit(limite);
  if (error) throw error;

  return (data ?? []).map((r: RawAviso) => mapearAviso(r, fuente));
}

export async function obtenerFiltrosDisponibles(): Promise<FiltrosDisponibles> {
  const columnaDeCadaFuente = (columna: string) =>
    Promise.all(FUENTES.map((fuente) => desde(fuente, columna).not(columna, 'is', null)));

  const [resMarca, resAnio, resCombustible] = await Promise.all([
    columnaDeCadaFuente('marca'),
    columnaDeCadaFuente('anio'),
    columnaDeCadaFuente('combustible'),
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
