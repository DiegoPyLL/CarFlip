import { supabase } from './client';

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
    { etiqueta: 'Hasta $5M',  min: 0,          max: 5_000_000 },
    { etiqueta: '$5M — $10M', min: 5_000_000,  max: 10_000_000 },
    { etiqueta: '$10M — $20M',min: 10_000_000, max: 20_000_000 },
    { etiqueta: '$20M — $35M',min: 20_000_000, max: 35_000_000 },
    { etiqueta: 'Más de $35M',min: 35_000_000, max: Infinity },
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

export async function obtenerDatosMarca(marca: string): Promise<{
  modelos: EstadisticaModelo[];
  distribucion: { etiqueta: string; min: number; max: number; total: number }[];
  precio_promedio: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
  total: number;
  anios: { anio: number; total: number; precio_promedio: number | null }[];
}> {
  type Fila = { modelo: string | null; precio: string | null; anio: number | null };

  async function fetchTabla(tabla: string): Promise<Fila[]> {
    const { data } = await supabase
      .from(tabla)
      .select('modelo, precio, anio')
      .ilike('marca', marca)
      .limit(5000);
    return (data ?? []) as Fila[];
  }

  const [ac, yp] = await Promise.all([
    fetchTabla('autocosmos_listings'),
    fetchTabla('yapo_listings'),
  ]);
  const rows = [...ac, ...yp];

  // Modelos
  const modeloMap = new Map<string, { total: number; precios: number[] }>();
  for (const row of rows) {
    if (!row.modelo) continue;
    const entry = modeloMap.get(row.modelo) ?? { total: 0, precios: [] };
    entry.total++;
    if (row.precio) entry.precios.push(parseFloat(row.precio));
    modeloMap.set(row.modelo, entry);
  }

  const modelos: EstadisticaModelo[] = Array.from(modeloMap.entries())
    .map(([modelo, { total, precios }]) => ({
      modelo,
      marca,
      total,
      precio_promedio: precios.length ? precios.reduce((a, b) => a + b, 0) / precios.length : null,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 12);

  // Stats globales de la marca
  const todosPrecios = rows
    .map(r => r.precio ? parseFloat(r.precio) : null)
    .filter((p): p is number => p !== null);

  const precio_promedio = todosPrecios.length ? todosPrecios.reduce((a, b) => a + b, 0) / todosPrecios.length : null;
  const precio_minimo   = todosPrecios.length ? Math.min(...todosPrecios) : null;
  const precio_maximo   = todosPrecios.length ? Math.max(...todosPrecios) : null;

  // Distribución por año
  const anioMap = new Map<number, { total: number; precios: number[] }>();
  for (const row of rows) {
    if (!row.anio) continue;
    const entry = anioMap.get(row.anio) ?? { total: 0, precios: [] };
    entry.total++;
    if (row.precio) entry.precios.push(parseFloat(row.precio));
    anioMap.set(row.anio, entry);
  }

  const anios = Array.from(anioMap.entries())
    .map(([anio, { total, precios }]) => ({
      anio,
      total,
      precio_promedio: precios.length ? precios.reduce((a, b) => a + b, 0) / precios.length : null,
    }))
    .sort((a, b) => b.anio - a.anio)
    .slice(0, 15);

  // Distribución de precios
  const brackets = [
    { etiqueta: 'Hasta $5M',  min: 0,          max: 5_000_000 },
    { etiqueta: '$5M — $10M', min: 5_000_000,  max: 10_000_000 },
    { etiqueta: '$10M — $20M',min: 10_000_000, max: 20_000_000 },
    { etiqueta: '$20M — $35M',min: 20_000_000, max: 35_000_000 },
    { etiqueta: 'Más de $35M',min: 35_000_000, max: Infinity },
  ];

  const distribucion = brackets.map(b => ({
    ...b,
    total: rows.filter(r => {
      const p = r.precio ? parseFloat(r.precio) : null;
      return p !== null && p >= b.min && p < b.max;
    }).length,
  }));

  return { modelos, distribucion, precio_promedio, precio_minimo, precio_maximo, total: rows.length, anios };
}
