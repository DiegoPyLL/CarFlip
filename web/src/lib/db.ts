import postgres from 'postgres';
import type { Aviso, FiltrosAviso, PaginaResultado, FiltrosDisponibles, Estadisticas } from './tipos';

const sql = postgres(process.env.DATABASE_URL!, {
  max: 1,
  idle_timeout: 20,
  connect_timeout: 10,
  ssl: process.env.USE_SSL === 'true' ? { rejectUnauthorized: false } : false,
});

const POR_PAGINA = 24;

type RawAviso = {
  id: number;
  fuente: string;
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
  primera_vez_visto: Date | null;
  ultima_vez_visto: Date | null;
  total_count: string;
};

function mapearAviso(row: RawAviso, fuente: 'autocosmos' | 'mercadolibre'): Aviso {
  return {
    ...row,
    fuente,
    precio: row.precio !== null ? parseFloat(row.precio) : null,
    precio_anterior: row.precio_anterior !== null ? parseFloat(row.precio_anterior) : null,
  };
}

export async function obtenerAvisos(filtros: FiltrosAviso): Promise<PaginaResultado<Aviso>> {
  const pagina = filtros.pagina ?? 1;
  const offset = (pagina - 1) * POR_PAGINA;

  const condiciones = (alias: string) => {
    const partes: string[] = [];
    if (filtros.marca) partes.push(`${alias}.marca ILIKE '%${filtros.marca.replace(/'/g, "''")}%'`);
    if (filtros.modelo) partes.push(`${alias}.modelo ILIKE '%${filtros.modelo.replace(/'/g, "''")}%'`);
    if (filtros.anio) partes.push(`${alias}.anio = ${filtros.anio}`);
    if (filtros.precio_min) partes.push(`${alias}.precio >= ${filtros.precio_min}`);
    if (filtros.precio_max) partes.push(`${alias}.precio <= ${filtros.precio_max}`);
    if (filtros.km_max) partes.push(`${alias}.km <= ${filtros.km_max}`);
    if (filtros.combustible) partes.push(`${alias}.combustible ILIKE '%${filtros.combustible.replace(/'/g, "''")}%'`);
    return partes.length > 0 ? 'WHERE ' + partes.join(' AND ') : '';
  };

  let rows: RawAviso[];

  if (filtros.fuente === 'autocosmos') {
    rows = await sql<RawAviso[]>`
      SELECT id, 'autocosmos' AS fuente, id_externo, url, titulo, precio::text, moneda,
             marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
             disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto,
             COUNT(*) OVER() AS total_count
      FROM autocosmos_listings
      ${sql.unsafe(condiciones('autocosmos_listings'))}
      ORDER BY ultima_vez_visto DESC NULLS LAST
      LIMIT ${POR_PAGINA} OFFSET ${offset}
    `;
  } else if (filtros.fuente === 'mercadolibre') {
    rows = await sql<RawAviso[]>`
      SELECT id, 'mercadolibre' AS fuente, id_externo, url, titulo, precio::text, moneda,
             marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
             disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto,
             COUNT(*) OVER() AS total_count
      FROM mercadolibre_listings
      ${sql.unsafe(condiciones('mercadolibre_listings'))}
      ORDER BY ultima_vez_visto DESC NULLS LAST
      LIMIT ${POR_PAGINA} OFFSET ${offset}
    `;
  } else {
    rows = await sql<RawAviso[]>`
      SELECT * FROM (
        SELECT id, 'autocosmos' AS fuente, id_externo, url, titulo, precio::text, moneda,
               marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
               disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto
        FROM autocosmos_listings
        ${sql.unsafe(condiciones('autocosmos_listings'))}
        UNION ALL
        SELECT id, 'mercadolibre' AS fuente, id_externo, url, titulo, precio::text, moneda,
               marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
               disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto
        FROM mercadolibre_listings
        ${sql.unsafe(condiciones('mercadolibre_listings'))}
      ) combined,
      LATERAL (SELECT COUNT(*) OVER() AS total_count) c
      ORDER BY ultima_vez_visto DESC NULLS LAST
      LIMIT ${POR_PAGINA} OFFSET ${offset}
    `;
  }

  const total = rows.length > 0 ? parseInt(rows[0].total_count) : 0;
  const items = rows.map((r) => mapearAviso(r, r.fuente as 'autocosmos' | 'mercadolibre'));

  return {
    items,
    total,
    pagina,
    total_paginas: Math.ceil(total / POR_PAGINA),
    por_pagina: POR_PAGINA,
  };
}

export async function obtenerAviso(id: number): Promise<Aviso | null> {
  const [autoRow] = await sql<RawAviso[]>`
    SELECT id, 'autocosmos' AS fuente, id_externo, url, titulo, precio::text, moneda,
           marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
           disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto,
           '1' AS total_count
    FROM autocosmos_listings WHERE id = ${id}
  `;
  if (autoRow) return mapearAviso(autoRow, 'autocosmos');

  const [mlRow] = await sql<RawAviso[]>`
    SELECT id, 'mercadolibre' AS fuente, id_externo, url, titulo, precio::text, moneda,
           marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
           disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto,
           '1' AS total_count
    FROM mercadolibre_listings WHERE id = ${id}
  `;
  if (mlRow) return mapearAviso(mlRow, 'mercadolibre');

  return null;
}

export async function obtenerFiltrosDisponibles(): Promise<FiltrosDisponibles> {
  const [marcasAC, marcasML, aniosAC, aniosML, combustiblesAC, combustiblesML] = await Promise.all([
    sql<{ marca: string }[]>`SELECT DISTINCT marca FROM autocosmos_listings WHERE marca IS NOT NULL ORDER BY marca`,
    sql<{ marca: string }[]>`SELECT DISTINCT marca FROM mercadolibre_listings WHERE marca IS NOT NULL ORDER BY marca`,
    sql<{ anio: number }[]>`SELECT DISTINCT anio FROM autocosmos_listings WHERE anio IS NOT NULL ORDER BY anio DESC`,
    sql<{ anio: number }[]>`SELECT DISTINCT anio FROM mercadolibre_listings WHERE anio IS NOT NULL ORDER BY anio DESC`,
    sql<{ combustible: string }[]>`SELECT DISTINCT combustible FROM autocosmos_listings WHERE combustible IS NOT NULL ORDER BY combustible`,
    sql<{ combustible: string }[]>`SELECT DISTINCT combustible FROM mercadolibre_listings WHERE combustible IS NOT NULL ORDER BY combustible`,
  ]);

  const marcas = [...new Set([...marcasAC.map((r) => r.marca), ...marcasML.map((r) => r.marca)])].sort();
  const anios = [...new Set([...aniosAC.map((r) => r.anio), ...aniosML.map((r) => r.anio)])].sort((a, b) => b - a);
  const combustibles = [...new Set([...combustiblesAC.map((r) => r.combustible), ...combustiblesML.map((r) => r.combustible)])].sort();

  return { marcas, anios, combustibles };
}

export async function obtenerEstadisticas(): Promise<Estadisticas> {
  const [statsAC, statsML] = await Promise.all([
    sql<{ total: string; precio_promedio: string | null; precio_minimo: string | null; precio_maximo: string | null; ultima: Date | null }[]>`
      SELECT COUNT(*) AS total, AVG(precio) AS precio_promedio, MIN(precio) AS precio_minimo,
             MAX(precio) AS precio_maximo, MAX(ultima_vez_visto) AS ultima
      FROM autocosmos_listings
    `,
    sql<{ total: string; precio_promedio: string | null; precio_minimo: string | null; precio_maximo: string | null; ultima: Date | null }[]>`
      SELECT COUNT(*) AS total, AVG(precio) AS precio_promedio, MIN(precio) AS precio_minimo,
             MAX(precio) AS precio_maximo, MAX(ultima_vez_visto) AS ultima
      FROM mercadolibre_listings
    `,
  ]);

  const ac = statsAC[0];
  const ml = statsML[0];
  const totalAC = parseInt(ac.total);
  const totalML = parseInt(ml.total);
  const total = totalAC + totalML;

  const promedioAC = ac.precio_promedio !== null ? parseFloat(ac.precio_promedio) : null;
  const promedioML = ml.precio_promedio !== null ? parseFloat(ml.precio_promedio) : null;

  let precio_promedio: number | null = null;
  if (promedioAC !== null && promedioML !== null && total > 0) {
    precio_promedio = (promedioAC * totalAC + promedioML * totalML) / total;
  } else if (promedioAC !== null) {
    precio_promedio = promedioAC;
  } else if (promedioML !== null) {
    precio_promedio = promedioML;
  }

  const minimoAC = ac.precio_minimo !== null ? parseFloat(ac.precio_minimo) : null;
  const minimoML = ml.precio_minimo !== null ? parseFloat(ml.precio_minimo) : null;
  const maximoAC = ac.precio_maximo !== null ? parseFloat(ac.precio_maximo) : null;
  const maximoML = ml.precio_maximo !== null ? parseFloat(ml.precio_maximo) : null;

  const precio_minimo = minimoAC !== null && minimoML !== null ? Math.min(minimoAC, minimoML)
    : minimoAC ?? minimoML;
  const precio_maximo = maximoAC !== null && maximoML !== null ? Math.max(maximoAC, maximoML)
    : maximoAC ?? maximoML;

  const ultimaAC = ac.ultima;
  const ultimaML = ml.ultima;
  const ultima_actualizacion = ultimaAC && ultimaML ? (ultimaAC > ultimaML ? ultimaAC : ultimaML)
    : ultimaAC ?? ultimaML;

  return {
    total_avisos: total,
    total_autocosmos: totalAC,
    total_mercadolibre: totalML,
    precio_promedio,
    precio_minimo,
    precio_maximo,
    ultima_actualizacion,
  };
}
