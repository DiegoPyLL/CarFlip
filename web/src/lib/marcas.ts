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
    const precio = fila.precio ? parseFloat(fila.precio) : NaN;
    if (Number.isFinite(precio) && precio > 0) entrada.precios.push(precio);
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
