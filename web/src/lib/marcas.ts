/** Una marca del catálogo tal como la publican /marcas y sitemap-marcas.xml. */
export interface MarcaListada {
  /** Forma canónica de la URL: /marcas/{slug}. El resto de las grafías redirige a ella. */
  slug: string;
  /** La grafía del catálogo, para mostrar ("Kia", no "kia"). */
  nombre: string;
  total: number;
  precio_minimo: number | null;
  precio_maximo: number | null;
}

/**
 * Cuántos avisos activos exige una página de modelo y una de año para existir.
 *
 * Es un parámetro del catálogo, no una constante estética: por debajo del mínimo
 * la página sería una ficha sola repetida bajo otra URL, y son miles de esas las
 * que se comen el presupuesto de rastreo. Al subir el catálogo, subirlos.
 */
export const MIN_AVISOS_MODELO = 5;
export const MIN_AVISOS_ANIO = 3;

/** Un modelo del catálogo con página propia: /marcas/{marca}/{slug}. */
export interface ModeloListado {
  slug: string;
  /** La grafía del catálogo, para mostrar ("CX-5", no "cx-5"). */
  nombre: string;
  /** Todas las grafías que colapsan a este slug, para consultar los avisos. */
  grafias: string[];
  total: number;
  precio_promedio: number | null;
}

/** Un año de un modelo con página propia: /marcas/{marca}/{modelo}/{anio}. */
export interface AnioListado {
  anio: number;
  total: number;
  precio_promedio: number | null;
}

/**
 * El precio de una fila, o `null` si no sirve como precio de venta.
 *
 * Postgres serializa `numeric` como cadena, y el catálogo trae ceros, negativos
 * y basura. Un `Math.min()` sobre esos valores pintaría Infinity como si fuera
 * un precio real.
 */
export function aPrecio(valor: string | null): number | null {
  const precio = valor ? parseFloat(valor) : NaN;
  return Number.isFinite(precio) && precio > 0 ? precio : null;
}

export function promedio(valores: number[]): number | null {
  return valores.length ? valores.reduce((a, b) => a + b, 0) / valores.length : null;
}

/**
 * Slug de un modelo para la URL /marcas/{marca}/{modelo}.
 *
 * A diferencia del slug de marca, este **no es reversible**: "Serie 3", "Serie-3"
 * y "Serie/3" dan todos `serie-3`. No hace falta que lo sea, porque la página no
 * reconstruye la grafía sino que busca, entre los modelos de la marca, los que
 * producen este slug —de ahí `grafias`—. La ventaja es que dos escrituras del
 * mismo modelo son una página con los avisos de ambas, y no dos URLs que compiten.
 *
 * Todo lo que no es letra ni número separa: un `/` sin traducir añadiría un
 * segmento a la ruta y la página dejaría de existir.
 */
export function slugModelo(nombre: string): string {
  return nombre
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Los modelos de una marca que superan el mínimo de avisos, de mayor a menor.
 *
 * Es la fuente única de qué páginas de modelo existen: la consumen la página, los
 * enlaces de /marcas/{marca} y sitemap-marcas.xml. Sin el mínimo, marca × modelo
 * son decenas de miles de URLs con uno o dos avisos cada una.
 */
export function paginasModelo(
  filas: { modelo: string | null; precio: string | null }[],
  minimo: number,
): ModeloListado[] {
  const mapa = new Map<string, { nombre: string; grafias: Set<string>; total: number; precios: number[] }>();

  for (const fila of filas) {
    if (!fila.modelo) continue;
    const slug = slugModelo(fila.modelo);
    // Un modelo que se queda sin slug —"---", "?"— no tiene URL que lo nombre.
    if (!slug) continue;

    const entrada = mapa.get(slug) ?? { nombre: fila.modelo, grafias: new Set(), total: 0, precios: [] };
    entrada.grafias.add(fila.modelo);
    entrada.total++;
    const precio = aPrecio(fila.precio);
    if (precio !== null) entrada.precios.push(precio);
    mapa.set(slug, entrada);
  }

  return Array.from(mapa.entries())
    .filter(([, { total }]) => total >= minimo)
    .map(([slug, { nombre, grafias, total, precios }]) => ({
      slug,
      nombre,
      grafias: [...grafias],
      total,
      precio_promedio: promedio(precios),
    }))
    .sort((a, b) => b.total - a.total);
}

/**
 * Los años de un modelo que superan el mínimo de avisos, del más nuevo al más
 * viejo. Misma función para la página, sus enlaces y el sitemap.
 *
 * No hace falta validar el rango del año aparte: solo existen los que están en
 * el catálogo, así que /marcas/toyota/yaris/99999 no aparece acá y es un 404.
 */
export function paginasAnio(
  filas: { anio: number | null; precio: string | null }[],
  minimo: number,
): AnioListado[] {
  const mapa = new Map<number, { total: number; precios: number[] }>();

  for (const fila of filas) {
    if (!fila.anio) continue;
    const entrada = mapa.get(fila.anio) ?? { total: 0, precios: [] };
    entrada.total++;
    const precio = aPrecio(fila.precio);
    if (precio !== null) entrada.precios.push(precio);
    mapa.set(fila.anio, entrada);
  }

  return Array.from(mapa.entries())
    .filter(([, { total }]) => total >= minimo)
    .map(([anio, { total, precios }]) => ({ anio, total, precio_promedio: promedio(precios) }))
    .sort((a, b) => b.anio - a.anio);
}

/**
 * Agrupa las filas del catálogo por marca. Decide qué páginas de marca existen,
 * porque la consumen tanto el hub /marcas como sitemap-marcas.xml.
 *
 * Vive fuera de `db/` —que arrastra el cliente de Supabase y sus credenciales—
 * para poder probarse directa, igual que `filtros.ts` o `enlaces.ts`.
 *
 * El slug es la marca en minúsculas y **sin recortar espacios**: la página de
 * marca resuelve con `ilike('marca', slug)`, que no los recorta, así que un trim
 * acá produciría un enlace y una entrada de sitemap que responden 404.
 */
export function agruparMarcas(
  filas: { marca: string | null; precio: string | null }[],
): MarcaListada[] {
  const mapa = new Map<string, { nombre: string; total: number; precios: number[] }>();

  for (const fila of filas) {
    if (!fila.marca) continue;
    const slug = fila.marca.toLowerCase();
    // La primera grafía vista gana, igual que en `obtenerDatosMarca`: el hub y la
    // página de la marca tienen que llamarla del mismo modo.
    const entrada = mapa.get(slug) ?? { nombre: fila.marca, total: 0, precios: [] };
    entrada.total++;
    const precio = aPrecio(fila.precio);
    if (precio !== null) entrada.precios.push(precio);
    mapa.set(slug, entrada);
  }

  return Array.from(mapa.entries())
    .map(([slug, { nombre, total, precios }]) => ({
      slug,
      nombre,
      total,
      // `null` y no `Math.min()` sin argumentos, que devuelve Infinity y se
      // pintaría como un precio real en la tarjeta del hub.
      precio_minimo: precios.length ? Math.min(...precios) : null,
      precio_maximo: precios.length ? Math.max(...precios) : null,
    }))
    .sort((a, b) => b.total - a.total);
}
