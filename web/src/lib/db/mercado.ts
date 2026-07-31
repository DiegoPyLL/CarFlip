import { supabase } from './client';
import { obtenerAvisosModelo } from './avisos';
import { FUENTES, TABLA_POR_FUENTE, soloPublicados } from './fuentes';
import {
  MIN_AVISOS_ANIO,
  MIN_AVISOS_MODELO,
  aPrecio,
  agruparMarcas,
  paginasAnio,
  paginasModelo,
  promedio,
  slugModelo,
  type AnioListado,
  type MarcaListada,
  type ModeloListado,
} from '../marcas';
import type { Aviso } from '../tipos';

export interface EstadisticaMarca {
  marca: string;
  total: number;
  precio_promedio: number | null;
  precio_mediano: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
}

export interface EstadisticaModelo {
  modelo: string;
  marca: string;
  total: number;
  precio_promedio: number | null;
}

/** Un tramo de un histograma. `max` puede ser Infinity en el último tramo. */
export interface BucketHistograma {
  etiqueta: string;
  min: number;
  max: number;
  total: number;
}

/** Percentiles de precio para un año (curva de depreciación). */
export interface PrecioAnio {
  anio: number;
  p25: number;
  mediana: number;
  p75: number;
  total: number;
}

/** Un día de la serie "nuevos avisos por día". */
export interface PuntoDia {
  fecha: string; // 'YYYY-MM-DD'
  total: number;
}

export interface DatosMercado {
  marcas: EstadisticaMarca[];
  modelos: EstadisticaModelo[];
  histogramaPrecio: BucketHistograma[];
  histogramaKm: BucketHistograma[];
  precioPorAnio: PrecioAnio[];
  mixCombustible: { etiqueta: string; total: number }[];
  nuevosPorDia: PuntoDia[];
  // KPIs
  total: number;
  precio_promedio: number | null;
  precio_mediano: number | null;
  nuevos_24h: number;
  con_baja: number;
  // Opciones para el consultor de precios, derivadas de las filas ya traídas
  // (evita consultas extra en el hot path).
  marcasTodas: string[];
  modelosTodos: string[];
  aniosTodos: number[];
}

// ── Utilidades de agregación ──────────────────────────────────────────
// Percentil por interpolación lineal sobre un arreglo YA ordenado ascendente.
function percentil(ordenados: number[], p: number): number {
  if (ordenados.length === 0) return 0;
  if (ordenados.length === 1) return ordenados[0];
  const idx = (ordenados.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return ordenados[lo];
  return ordenados[lo] + (ordenados[hi] - ordenados[lo]) * (idx - lo);
}

// Cuenta `valores` en los tramos definidos por `edges` (n+1 bordes → n tramos).
// `fmt` construye la etiqueta corta de cada tramo a partir de sus bordes.
function histograma(
  valores: number[],
  edges: number[],
  fmt: (min: number, max: number) => string,
): BucketHistograma[] {
  const buckets: BucketHistograma[] = edges.slice(0, -1).map((min, i) => ({
    min,
    max: edges[i + 1],
    total: 0,
    etiqueta: fmt(min, edges[i + 1]),
  }));
  for (const v of valores) {
    for (const b of buckets) {
      if (v >= b.min && v < b.max) {
        b.total++;
        break;
      }
    }
  }
  return buckets;
}

// Bordes de precio (CLP): más resolución en el tramo $5M–$20M, donde se
// concentra el mercado de usados chileno, y una cola larga hacia arriba.
const EDGES_PRECIO = [
  0, 3e6, 5e6, 7e6, 9e6, 11e6, 13e6, 16e6, 20e6, 25e6, 32e6, 42e6, 60e6, Infinity,
];
const EDGES_KM = [0, 20e3, 40e3, 60e3, 80e3, 100e3, 120e3, 150e3, 200e3, Infinity];

const etiquetaPrecio = (min: number, max: number) =>
  max === Infinity ? `${min / 1e6}M+` : `${min / 1e6}M`;
const etiquetaKm = (min: number, max: number) =>
  max === Infinity ? `${min / 1e3}k+` : `${min / 1e3}k`;

// Combustible viene como texto libre y con muchas variantes ortográficas; se
// normaliza a un set canónico. Devuelve null si el campo está vacío para no
// inflar "Otros" con avisos que simplemente no traen el dato.
function normalizarCombustible(v: string | null): string | null {
  if (!v) return null;
  const s = v.toLowerCase();
  if (s.includes('bencina') || s.includes('gasolina') || s.includes('nafta')) return 'Bencina';
  if (s.includes('diés') || s.includes('dies') || s.includes('petról') || s.includes('petrol'))
    return 'Diésel';
  if (s.includes('híb') || s.includes('hib') || s.includes('hybrid')) return 'Híbrido';
  if (s.includes('eléc') || s.includes('elec')) return 'Eléctrico';
  return 'Otros';
}
// Orden fijo → el color sigue a la categoría, no a su ranking (ver DESIGN.md).
const ORDEN_COMBUSTIBLE = ['Bencina', 'Diésel', 'Híbrido', 'Eléctrico', 'Otros'];

const DIAS_SERIE = 14; // ventana del sparkline "nuevos por día"
const ANIO_MIN = 1990;
const MIN_POR_ANIO = 5; // años con menos avisos no dan una banda de percentiles fiable

const claveDia = (t: number) => new Date(t).toISOString().slice(0, 10);

export async function obtenerDatosMercado(): Promise<DatosMercado> {
  type Fila = {
    marca: string | null;
    modelo: string | null;
    precio: string | null;
    anio: number | null;
    km: number | null;
    combustible: string | null;
    delta_pct: number | null;
    primera_vez_visto: string | null;
  };

  async function fetchFuente(f: Aviso['fuente']): Promise<Fila[]> {
    const { data } = await soloPublicados(
      supabase
        .from(TABLA_POR_FUENTE[f])
        .select('marca, modelo, precio, anio, km, combustible, delta_pct, primera_vez_visto'),
      f,
    )
      .not('marca', 'is', null)
      .limit(10000);
    return (data ?? []) as Fila[];
  }

  const resultados = await Promise.all(FUENTES.map((f) => fetchFuente(f)));
  const rows = resultados.flat();

  // ── Estructuras acumuladas en una sola pasada ───────────────────────
  const marcaMap = new Map<string, { total: number; precios: number[] }>();
  const modeloMap = new Map<string, { marca: string; total: number; precios: number[] }>();
  const marcasSet = new Set<string>();
  const modelosSet = new Set<string>();
  const aniosSet = new Set<number>();
  const preciosGlobal: number[] = [];
  const kmGlobal: number[] = [];
  const anioPrecios = new Map<number, number[]>();
  const combustibleMap = new Map<string, number>();

  const ahora = Date.now();
  const hace24h = ahora - 24 * 3600 * 1000;
  const anioMax = new Date().getFullYear() + 1;

  // Serie de días inicializada en 0 para que no queden huecos en el sparkline.
  const mapaDias = new Map<string, number>();
  for (let i = DIAS_SERIE - 1; i >= 0; i--) {
    mapaDias.set(claveDia(ahora - i * 24 * 3600 * 1000), 0);
  }

  let nuevos_24h = 0;
  let con_baja = 0;

  for (const row of rows) {
    const precioRaw = row.precio ? parseFloat(row.precio) : NaN;
    const precio = Number.isFinite(precioRaw) && precioRaw > 0 ? precioRaw : null;

    if (row.marca) marcasSet.add(row.marca);
    if (row.modelo) modelosSet.add(row.modelo);
    if (row.anio && row.anio >= ANIO_MIN && row.anio <= anioMax) aniosSet.add(row.anio);

    if (row.marca) {
      const e = marcaMap.get(row.marca) ?? { total: 0, precios: [] };
      e.total++;
      if (precio !== null) e.precios.push(precio);
      marcaMap.set(row.marca, e);
    }

    if (row.marca && row.modelo) {
      const key = `${row.marca}||${row.modelo}`;
      const e = modeloMap.get(key) ?? { marca: row.marca, total: 0, precios: [] };
      e.total++;
      if (precio !== null) e.precios.push(precio);
      modeloMap.set(key, e);
    }

    if (precio !== null) {
      preciosGlobal.push(precio);
      if (row.anio && row.anio >= ANIO_MIN && row.anio <= anioMax) {
        const arr = anioPrecios.get(row.anio) ?? [];
        arr.push(precio);
        anioPrecios.set(row.anio, arr);
      }
    }

    if (row.km !== null && row.km > 0) kmGlobal.push(row.km);

    const comb = normalizarCombustible(row.combustible);
    if (comb) combustibleMap.set(comb, (combustibleMap.get(comb) ?? 0) + 1);

    if (row.delta_pct !== null && row.delta_pct < 0) con_baja++;

    if (row.primera_vez_visto) {
      const t = Date.parse(row.primera_vez_visto);
      if (!Number.isNaN(t)) {
        if (t >= hace24h) nuevos_24h++;
        const k = claveDia(t);
        if (mapaDias.has(k)) mapaDias.set(k, (mapaDias.get(k) ?? 0) + 1);
      }
    }
  }

  // ── Marcas (con mediana para el dumbbell) ───────────────────────────
  const marcas: EstadisticaMarca[] = Array.from(marcaMap.entries())
    .map(([marca, { total, precios }]) => {
      const ordenados = [...precios].sort((a, b) => a - b);
      return {
        marca,
        total,
        precio_promedio: promedio(precios),
        precio_mediano: ordenados.length ? percentil(ordenados, 0.5) : null,
        precio_minimo: ordenados.length ? ordenados[0] : null,
        precio_maximo: ordenados.length ? ordenados[ordenados.length - 1] : null,
      };
    })
    .sort((a, b) => b.total - a.total)
    .slice(0, 20);

  // ── Modelos ─────────────────────────────────────────────────────────
  const modelos: EstadisticaModelo[] = Array.from(modeloMap.entries())
    .map(([key, { marca, total, precios }]) => ({
      modelo: key.split('||')[1],
      marca,
      total,
      precio_promedio: promedio(precios),
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 15);

  // ── Histogramas ─────────────────────────────────────────────────────
  const histogramaPrecio = histograma(preciosGlobal, EDGES_PRECIO, etiquetaPrecio);
  const histogramaKm = histograma(kmGlobal, EDGES_KM, etiquetaKm);

  // ── Precio por año (percentiles) ────────────────────────────────────
  const precioPorAnio: PrecioAnio[] = Array.from(anioPrecios.entries())
    .filter(([, precios]) => precios.length >= MIN_POR_ANIO)
    .map(([anio, precios]) => {
      const ordenados = precios.sort((a, b) => a - b);
      return {
        anio,
        p25: percentil(ordenados, 0.25),
        mediana: percentil(ordenados, 0.5),
        p75: percentil(ordenados, 0.75),
        total: ordenados.length,
      };
    })
    .sort((a, b) => a.anio - b.anio);

  // ── Mix de combustible (orden canónico fijo) ────────────────────────
  const mixCombustible = ORDEN_COMBUSTIBLE.map((etiqueta) => ({
    etiqueta,
    total: combustibleMap.get(etiqueta) ?? 0,
  })).filter((c) => c.total > 0);

  // ── Serie de nuevos por día (más antiguo → más nuevo) ───────────────
  const nuevosPorDia: PuntoDia[] = Array.from(mapaDias.entries()).map(([fecha, total]) => ({
    fecha,
    total,
  }));

  // ── KPIs de precio global ───────────────────────────────────────────
  const preciosOrdenados = preciosGlobal.sort((a, b) => a - b);
  const precio_promedio = promedio(preciosOrdenados);
  const precio_mediano = preciosOrdenados.length ? percentil(preciosOrdenados, 0.5) : null;

  return {
    marcas,
    modelos,
    histogramaPrecio,
    histogramaKm,
    precioPorAnio,
    mixCombustible,
    nuevosPorDia,
    total: rows.length,
    precio_promedio,
    precio_mediano,
    nuevos_24h,
    con_baja,
    marcasTodas: [...marcasSet].sort((a, b) => a.localeCompare(b, 'es')),
    modelosTodos: [...modelosSet].sort((a, b) => a.localeCompare(b, 'es')),
    aniosTodos: [...aniosSet].sort((a, b) => b - a),
  };
}

/** Un día de la serie histórica leída de `market_snapshots`. */
export interface PuntoHistoria {
  fecha: string; // 'YYYY-MM-DD'
  total: number;
  precio_promedio: number | null;
  precio_mediano: number | null;
}

/**
 * Serie histórica de precios desde `market_snapshots` (una fila por día que
 * escribe `carflip snapshot`). Devuelve más antiguo → más nuevo, o `[]` si la
 * tabla aún no acumula filas — la UI degrada con gracia.
 *
 * Las filas previas al retiro de los scrapers agregan también esos avisos, así
 * que la serie tiene un escalón a la baja en esa fecha.
 */
export async function obtenerHistoriaMercado(dias = 30): Promise<PuntoHistoria[]> {
  const { data, error } = await supabase
    .from('market_snapshots')
    .select('fecha, total, precio_promedio, precio_mediano')
    .order('fecha', { ascending: false })
    .limit(dias);

  if (error || !data) return [];

  return (data as Record<string, unknown>[])
    .map((r) => ({
      fecha: String(r.fecha),
      total: Number(r.total ?? 0),
      precio_promedio: r.precio_promedio != null ? Number(r.precio_promedio) : null,
      precio_mediano: r.precio_mediano != null ? Number(r.precio_mediano) : null,
    }))
    .reverse();
}

/** Referencia de precio de mercado para un vehículo específico. */
export interface ConsultaMercado {
  marca: string;
  modelo: string;
  anio: number;
  /** Años ±N efectivamente usados para juntar los comparables. */
  banda: number;
  comparables: number;
  precio_min: number;
  p25: number;
  mediana: number;
  p75: number;
  precio_max: number;
  promedio: number;
  km_mediano: number | null;
}

/** Mínimo de comparables para que la mediana sea razonablemente estable. */
const MIN_COMPARABLES = 8;
/** Banda máxima de años que se acepta abrir para juntar comparables. */
const BANDA_MAX = 3;

/**
 * Agrupa los avisos con la misma marca/modelo y un año cercano, y devuelve los
 * percentiles de su precio. `null` si no hay ninguno con precio.
 *
 * La banda de años es adaptativa: parte en ±1 (como candidatos.sql) y solo se
 * abre —±2, ±3— si no reúne `MIN_COMPARABLES`. Con un catálogo de pocos miles de
 * avisos, una celda marca/modelo/año exacta suele tener 2-3 casos, y una mediana
 * sobre eso no dice nada. La banda usada se devuelve para poder declararla en la
 * UI en vez de esconder el ensanche. Se trae ±BANDA_MAX en una sola consulta y
 * el recorte se hace en memoria.
 */
export async function consultarMercado(
  marca: string,
  modelo: string,
  anio: number,
): Promise<ConsultaMercado | null> {
  type Fila = { precio: string | null; km: number | null; anio: number | null };

  async function fetchFuente(f: Aviso['fuente']): Promise<Fila[]> {
    const { data } = await soloPublicados(
      supabase.from(TABLA_POR_FUENTE[f]).select('precio, km, anio'),
      f,
    )
      .ilike('marca', marca)
      .ilike('modelo', modelo)
      .gte('anio', anio - BANDA_MAX)
      .lte('anio', anio + BANDA_MAX)
      .not('precio', 'is', null)
      .limit(3000);
    return (data ?? []) as Fila[];
  }

  const resultados = await Promise.all(FUENTES.map((f) => fetchFuente(f)));
  const candidatos = resultados
    .flat()
    .map((r) => ({ precio: r.precio ? parseFloat(r.precio) : NaN, km: r.km, anio: r.anio }))
    .filter((r) => Number.isFinite(r.precio) && r.precio > 0 && r.anio != null);

  if (candidatos.length === 0) return null;

  // La banda más angosta que llegue al mínimo; si ninguna llega, la más amplia.
  let banda = BANDA_MAX;
  let seleccion = candidatos;
  for (let b = 1; b <= BANDA_MAX; b++) {
    const subset = candidatos.filter((r) => Math.abs((r.anio as number) - anio) <= b);
    if (subset.length >= MIN_COMPARABLES) {
      banda = b;
      seleccion = subset;
      break;
    }
  }

  const precios = seleccion.map((r) => r.precio).sort((a, b) => a - b);
  const kms = seleccion
    .map((r) => r.km)
    .filter((k): k is number => k != null && k > 0)
    .sort((a, b) => a - b);

  return {
    marca,
    modelo,
    anio,
    banda,
    comparables: precios.length,
    precio_min: precios[0],
    p25: percentil(precios, 0.25),
    mediana: percentil(precios, 0.5),
    p75: percentil(precios, 0.75),
    precio_max: precios[precios.length - 1],
    promedio: precios.reduce((a, b) => a + b, 0) / precios.length,
    km_mediano: kms.length ? percentil(kms, 0.5) : null,
  };
}

/**
 * Clasifica un precio contra la mediana del mercado. La dirección la comunica el
 * glifo (▼/≈/▲), nunca el color: la paleta se mantiene acromática.
 */
export function posicionMercado(
  precio: number,
  mediana: number,
): { pct: number; etiqueta: string; glifo: string } {
  const pct = ((precio - mediana) / mediana) * 100;
  if (pct <= -10) return { pct, etiqueta: 'Bajo el mercado', glifo: '▼' };
  if (pct >= 10) return { pct, etiqueta: 'Sobre el mercado', glifo: '▲' };
  return { pct, etiqueta: 'En rango de mercado', glifo: '≈' };
}

/** Una fila del catálogo, con lo que agregan la página de marca y las de modelo. */
type FilaMarca = {
  marca: string | null;
  modelo: string | null;
  precio: string | null;
  anio: number | null;
  km: number | null;
};

/**
 * Las filas publicadas de una marca, de todas las fuentes.
 *
 * La marca va por `ilike` sin comodines —coincidencia exacta, sin distinguir
 * mayúsculas—: el slug de la URL viene en minúsculas y el catálogo la escribe
 * como quiere. Un `%marca%` haría que /marcas/mini arrastrara "Mini Cooper".
 */
async function filasDeMarca(marca: string): Promise<FilaMarca[]> {
  const porFuente = await Promise.all(
    FUENTES.map(async (f) => {
      const { data } = await soloPublicados(
        supabase.from(TABLA_POR_FUENTE[f]).select('marca, modelo, precio, anio, km'),
        f,
      )
        .ilike('marca', marca)
        .limit(5000);
      return (data ?? []) as FilaMarca[];
    }),
  );
  return porFuente.flat();
}

export async function obtenerDatosMarca(marca: string): Promise<{
  /** Los 12 modelos más listados. `total` decide cuáles tienen página propia. */
  modelos: ModeloListado[];
  distribucion: { etiqueta: string; min: number; max: number; total: number }[];
  precio_promedio: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
  total: number;
  anios: AnioListado[];
  /** La marca con la grafía del catálogo: la URL viene en minúsculas y el `ilike` no la distingue. */
  nombre: string;
}> {
  const rows = await filasDeMarca(marca);

  // Sin filas la marca no existe en el catálogo y la página no se llega a
  // renderizar, así que el valor de reserva solo cubre el tipo.
  const nombre = rows.find((r) => r.marca)?.marca ?? marca;

  // Los modelos salen de la misma función que decide qué páginas de modelo
  // existen, con el mínimo en 1 para listarlos todos: así el enlace del hub y la
  // página que abre no pueden discrepar sobre el slug ni sobre el recuento.
  const modelos = paginasModelo(rows, 1).slice(0, 12);
  // Idem para los años, que acá se listan completos y en la página de modelo se
  // filtran por inventario.
  const anios = paginasAnio(rows, 1).slice(0, 15);

  // Stats globales de la marca
  const todosPrecios = rows.map((r) => aPrecio(r.precio)).filter((p): p is number => p !== null);

  const precio_promedio = promedio(todosPrecios);
  const precio_minimo   = todosPrecios.length ? Math.min(...todosPrecios) : null;
  const precio_maximo   = todosPrecios.length ? Math.max(...todosPrecios) : null;

  // Distribución de precios
  const brackets = [
    { etiqueta: 'Hasta $5M',  min: 0,          max: 5_000_000 },
    { etiqueta: '$5M — $10M', min: 5_000_000,  max: 10_000_000 },
    { etiqueta: '$10M — $20M',min: 10_000_000, max: 20_000_000 },
    { etiqueta: '$20M — $35M',min: 20_000_000, max: 35_000_000 },
    { etiqueta: 'Más de $35M',min: 35_000_000, max: Infinity },
  ];

  const distribucion = brackets.map((b) => ({
    ...b,
    total: todosPrecios.filter((p) => p >= b.min && p < b.max).length,
  }));

  return { modelos, distribucion, precio_promedio, precio_minimo, precio_maximo, total: rows.length, anios, nombre };
}

export interface DatosModelo {
  /** Grafías del catálogo, no los slugs de la URL ("Toyota", "Yaris"). */
  marca: string;
  modelo: string;
  slugMarca: string;
  slugModelo: string;
  /** El año de la vista, o `null` en la página del modelo completo. */
  anio: number | null;
  total: number;
  precio_promedio: number | null;
  precio_mediano: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
  km_mediano: number | null;
  /** Los años del modelo con página propia, incluido el de la vista. */
  anios: AnioListado[];
  histogramaPrecio: BucketHistograma[];
  histogramaKm: BucketHistograma[];
  /** Curva de depreciación del modelo. Vacía en la vista de un año. */
  precioPorAnio: PrecioAnio[];
  avisos: Aviso[];
}

/**
 * Los datos de /marcas/{marca}/{modelo} y de /marcas/{marca}/{modelo}/{anio}.
 *
 * Devuelve `null` cuando la página no existe —modelo desconocido, o inventario
 * bajo el mínimo—, y con eso la página responde 404. Es la misma decisión que ya
 * toma la de marca con `total === 0`: una URL sin contenido detrás no se sirve.
 *
 * El modelo se resuelve por slug sobre las filas de la marca en vez de con un
 * `ilike` sobre el modelo, porque el slug no es reversible: "Serie 3" y "Serie-3"
 * dan el mismo, y la página tiene que traer los avisos de ambas grafías.
 */
export async function obtenerDatosModelo(
  marcaSlug: string,
  modeloSlug: string,
  anio?: number,
): Promise<DatosModelo | null> {
  const filas = await filasDeMarca(marcaSlug);

  const modelo = paginasModelo(filas, MIN_AVISOS_MODELO).find((m) => m.slug === modeloSlug);
  if (!modelo) return null;

  const delModelo = filas.filter((f) => f.modelo && slugModelo(f.modelo) === modeloSlug);
  const anios = paginasAnio(delModelo, MIN_AVISOS_ANIO);

  // La vista de un año existe solo si ese año tiene página, así que el rango del
  // año no se valida aparte: /marcas/toyota/yaris/99999 no está en la lista.
  if (anio !== undefined && !anios.some((a) => a.anio === anio)) return null;

  const vista = anio !== undefined ? delModelo.filter((f) => f.anio === anio) : delModelo;

  const precios = vista.map((f) => aPrecio(f.precio)).filter((p): p is number => p !== null);
  const preciosOrdenados = [...precios].sort((a, b) => a - b);
  const kms = vista.map((f) => f.km).filter((k): k is number => k !== null && k >= 0);

  return {
    marca: filas.find((f) => f.marca)?.marca ?? marcaSlug,
    modelo: modelo.nombre,
    slugMarca: marcaSlug,
    slugModelo: modeloSlug,
    anio: anio ?? null,
    total: vista.length,
    precio_promedio: promedio(precios),
    precio_mediano: precios.length ? percentil(preciosOrdenados, 0.5) : null,
    precio_minimo: precios.length ? preciosOrdenados[0] : null,
    precio_maximo: precios.length ? preciosOrdenados[preciosOrdenados.length - 1] : null,
    km_mediano: kms.length ? percentil([...kms].sort((a, b) => a - b), 0.5) : null,
    anios,
    histogramaPrecio: histograma(precios, EDGES_PRECIO, etiquetaPrecio),
    histogramaKm: histograma(kms, EDGES_KM, etiquetaKm),
    precioPorAnio: anio !== undefined ? [] : curvaPorAnio(delModelo),
    avisos: await obtenerAvisosModelo(marcaSlug, modelo.grafias, anio),
  };
}

/**
 * Qué páginas de modelo y de año existen bajo una marca.
 *
 * La consume sitemap-marcas.xml. Sale de las mismas funciones que usa la página
 * para decidir si responde 200 o 404, así que el sitemap no puede declarar una
 * URL muerta ni omitir una viva.
 */
export async function obtenerPaginasDeMarca(
  marca: string,
): Promise<{ slug: string; anios: number[] }[]> {
  const filas = await filasDeMarca(marca);

  return paginasModelo(filas, MIN_AVISOS_MODELO).map(({ slug }) => ({
    slug,
    anios: paginasAnio(
      filas.filter((f) => f.modelo && slugModelo(f.modelo) === slug),
      MIN_AVISOS_ANIO,
    ).map((a) => a.anio),
  }));
}

/** Percentiles de precio por año de un modelo: su curva de depreciación. */
function curvaPorAnio(filas: FilaMarca[]): PrecioAnio[] {
  const porAnio = new Map<number, number[]>();
  for (const fila of filas) {
    const precio = aPrecio(fila.precio);
    if (!fila.anio || fila.anio < ANIO_MIN || precio === null) continue;
    porAnio.set(fila.anio, [...(porAnio.get(fila.anio) ?? []), precio]);
  }

  return Array.from(porAnio.entries())
    .filter(([, precios]) => precios.length >= MIN_POR_ANIO)
    .map(([anio, precios]) => {
      const ordenados = precios.sort((a, b) => a - b);
      return {
        anio,
        p25: percentil(ordenados, 0.25),
        mediana: percentil(ordenados, 0.5),
        p75: percentil(ordenados, 0.75),
        total: ordenados.length,
      };
    })
    .sort((a, b) => a.anio - b.anio);
}

/**
 * Todas las marcas con avisos publicados, de mayor a menor cantidad.
 *
 * Es la fuente única de "qué páginas de marca existen": la consumen el hub
 * /marcas y sitemap-marcas.xml, de modo que el sitemap no puede listar una URL
 * que el hub no enlaza ni al revés.
 */
export async function obtenerMarcas(): Promise<MarcaListada[]> {
  type Fila = { marca: string | null; precio: string | null };

  async function fetchFuente(f: Aviso['fuente']): Promise<Fila[]> {
    const { data } = await soloPublicados(
      supabase.from(TABLA_POR_FUENTE[f]).select('marca, precio'),
      f,
    )
      .not('marca', 'is', null)
      .limit(10000);
    return (data ?? []) as Fila[];
  }

  const resultados = await Promise.all(FUENTES.map((f) => fetchFuente(f)));
  return agruparMarcas(resultados.flat());
}
