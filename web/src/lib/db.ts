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

function mapearAviso(row: RawAviso, fuente: 'autocosmos' | 'yapo'): Aviso {
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

  const condicionesSql = () => sql`
    ${filtros.marca ? sql`AND marca ILIKE ${'%' + filtros.marca + '%'}` : sql``}
    ${filtros.modelo ? sql`AND modelo ILIKE ${'%' + filtros.modelo + '%'}` : sql``}
    ${filtros.anio ? sql`AND anio = ${filtros.anio}` : sql``}
    ${filtros.precio_min ? sql`AND precio >= ${filtros.precio_min}` : sql``}
    ${filtros.precio_max ? sql`AND precio <= ${filtros.precio_max}` : sql``}
    ${filtros.km_max ? sql`AND km <= ${filtros.km_max}` : sql``}
    ${filtros.combustible ? sql`AND combustible ILIKE ${'%' + filtros.combustible + '%'}` : sql``}
  `;

  const ordenarSql = () => {
    switch (filtros.orden) {
      case 'precio_asc':  return sql`ORDER BY precio ASC NULLS LAST`;
      case 'precio_desc': return sql`ORDER BY precio DESC NULLS LAST`;
      case 'km_asc':      return sql`ORDER BY km ASC NULLS LAST`;
      default:            return sql`ORDER BY ultima_vez_visto DESC NULLS LAST`;
    }
  };

  let rows: RawAviso[];

  if (filtros.fuente === 'autocosmos') {
    rows = await sql<RawAviso[]>`
      SELECT id, 'autocosmos' AS fuente, id_externo, url, titulo, precio::text, moneda,
             marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
             disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto,
             COUNT(*) OVER() AS total_count
      FROM autocosmos_listings
      WHERE 1=1 ${condicionesSql()}
      ${ordenarSql()}
      LIMIT ${POR_PAGINA} OFFSET ${offset}
    `;
  } else if (filtros.fuente === 'yapo') {
    rows = await sql<RawAviso[]>`
      SELECT id, 'yapo' AS fuente, id_externo, url, titulo, precio::text, moneda,
             marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
             disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto,
             COUNT(*) OVER() AS total_count
      FROM yapo_listings
      WHERE 1=1 ${condicionesSql()}
      ${ordenarSql()}
      LIMIT ${POR_PAGINA} OFFSET ${offset}
    `;
  } else {
    rows = await sql<RawAviso[]>`
      SELECT combined.*, COUNT(*) OVER() AS total_count FROM (
        SELECT id, 'autocosmos' AS fuente, id_externo, url, titulo, precio::text, moneda,
               marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
               disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto
        FROM autocosmos_listings
        WHERE 1=1 ${condicionesSql()}
        UNION ALL
        SELECT id, 'yapo' AS fuente, id_externo, url, titulo, precio::text, moneda,
               marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
               disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto
        FROM yapo_listings
        WHERE 1=1 ${condicionesSql()}
      ) combined
      ${ordenarSql()}
      LIMIT ${POR_PAGINA} OFFSET ${offset}
    `;
  }

  const total = rows.length > 0 ? parseInt(rows[0].total_count) : 0;
  const items = rows.map((r) => mapearAviso(r, r.fuente as 'autocosmos' | 'yapo'));

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

  const [yapoRow] = await sql<RawAviso[]>`
    SELECT id, 'yapo' AS fuente, id_externo, url, titulo, precio::text, moneda,
           marca, modelo, anio, km, ubicacion, combustible, descripcion, url_imagen,
           disponible, precio_anterior::text, delta_pct, primera_vez_visto, ultima_vez_visto,
           '1' AS total_count
    FROM yapo_listings WHERE id = ${id}
  `;
  return yapoRow ? mapearAviso(yapoRow, 'yapo') : null;
}

export async function obtenerFiltrosDisponibles(): Promise<FiltrosDisponibles> {
  const [marcasAC, marcasYP, aniosAC, aniosYP, combustiblesAC, combustiblesYP] = await Promise.all([
    sql<{ marca: string }[]>`SELECT DISTINCT marca FROM autocosmos_listings WHERE marca IS NOT NULL ORDER BY marca`,
    sql<{ marca: string }[]>`SELECT DISTINCT marca FROM yapo_listings WHERE marca IS NOT NULL ORDER BY marca`,
    sql<{ anio: number }[]>`SELECT DISTINCT anio FROM autocosmos_listings WHERE anio IS NOT NULL ORDER BY anio DESC`,
    sql<{ anio: number }[]>`SELECT DISTINCT anio FROM yapo_listings WHERE anio IS NOT NULL ORDER BY anio DESC`,
    sql<{ combustible: string }[]>`SELECT DISTINCT combustible FROM autocosmos_listings WHERE combustible IS NOT NULL ORDER BY combustible`,
    sql<{ combustible: string }[]>`SELECT DISTINCT combustible FROM yapo_listings WHERE combustible IS NOT NULL ORDER BY combustible`,
  ]);

  const marcas = [...new Set([...marcasAC.map((r) => r.marca), ...marcasYP.map((r) => r.marca)])].sort();
  const anios = [...new Set([...aniosAC.map((r) => r.anio), ...aniosYP.map((r) => r.anio)])].sort((a, b) => b - a);
  const combustibles = [...new Set([...combustiblesAC.map((r) => r.combustible), ...combustiblesYP.map((r) => r.combustible)])].sort();

  return { marcas, anios, combustibles };
}

export async function obtenerEstadisticas(): Promise<Estadisticas> {
  type StatsRow = { total: string; precio_promedio: string | null; precio_minimo: string | null; precio_maximo: string | null; ultima: Date | null };

  const [[ac], [yp]] = await Promise.all([
    sql<StatsRow[]>`
      SELECT COUNT(*) AS total, AVG(precio) AS precio_promedio, MIN(precio) AS precio_minimo,
             MAX(precio) AS precio_maximo, MAX(ultima_vez_visto) AS ultima
      FROM autocosmos_listings
    `,
    sql<StatsRow[]>`
      SELECT COUNT(*) AS total, AVG(precio) AS precio_promedio, MIN(precio) AS precio_minimo,
             MAX(precio) AS precio_maximo, MAX(ultima_vez_visto) AS ultima
      FROM yapo_listings
    `,
  ]);

  const totalAC = parseInt(ac.total);
  const totalYP = parseInt(yp.total);
  const total = totalAC + totalYP;

  const promedioAC = ac.precio_promedio !== null ? parseFloat(ac.precio_promedio) : null;
  const promedioYP = yp.precio_promedio !== null ? parseFloat(yp.precio_promedio) : null;

  let precio_promedio: number | null = null;
  if (promedioAC !== null && promedioYP !== null && total > 0) {
    precio_promedio = (promedioAC * totalAC + promedioYP * totalYP) / total;
  } else {
    precio_promedio = promedioAC ?? promedioYP;
  }

  const minimoAC = ac.precio_minimo !== null ? parseFloat(ac.precio_minimo) : null;
  const minimoYP = yp.precio_minimo !== null ? parseFloat(yp.precio_minimo) : null;
  const maximoAC = ac.precio_maximo !== null ? parseFloat(ac.precio_maximo) : null;
  const maximoYP = yp.precio_maximo !== null ? parseFloat(yp.precio_maximo) : null;

  const precio_minimo = minimoAC !== null && minimoYP !== null ? Math.min(minimoAC, minimoYP) : minimoAC ?? minimoYP;
  const precio_maximo = maximoAC !== null && maximoYP !== null ? Math.max(maximoAC, maximoYP) : maximoAC ?? maximoYP;

  const ultima_actualizacion = ac.ultima && yp.ultima ? (ac.ultima > yp.ultima ? ac.ultima : yp.ultima) : ac.ultima ?? yp.ultima;

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
