/**
 * El catálogo de marcas y modelos tal como lo consume el formulario de aviso.
 *
 * Vive fuera de `db/` —que arrastra el cliente de Supabase y sus credenciales—
 * para poder probarse directo, igual que `marcas.ts` o `filtros.ts`.
 */

/** Un modelo del catálogo. El `id` es lo único que viaja en el formulario. */
export interface ModeloCatalogo {
  id: number;
  modelo: string;
}

export interface MarcaCatalogo {
  marca: string;
  modelos: ModeloCatalogo[];
}

/** Una versión con su ficha. Los tres campos son los que el formulario rellena. */
export interface VersionCatalogo {
  version: string;
  combustible: string | null;
  transmision: string | null;
  traccion: string | null;
}

export interface FilaModelo {
  id: number;
  marca: string;
  modelo: string;
}

/**
 * Agrupa los modelos por marca, en orden alfabético dentro y fuera.
 *
 * Alfabético y no por volumen —al revés que el hub /marcas, que ordena por
 * cantidad de avisos— porque acá el usuario no explora: viene a encontrar su
 * auto en una lista de decenas de marcas, y para eso el orden predecible gana.
 *
 * Se agrupa por la grafía de la marca y no por su slug: el catálogo tiene una
 * única grafía por marca (lo garantiza el UNIQUE de `catalogo_modelos`), así
 * que aquí no hay nada que colapsar.
 */
export function agruparModelos(filas: FilaModelo[]): MarcaCatalogo[] {
  const mapa = new Map<string, ModeloCatalogo[]>();

  for (const fila of filas) {
    const modelos = mapa.get(fila.marca) ?? [];
    modelos.push({ id: fila.id, modelo: fila.modelo });
    mapa.set(fila.marca, modelos);
  }

  const alfabetico = (a: string, b: string) => a.localeCompare(b, 'es');

  return [...mapa.entries()]
    .map(([marca, modelos]) => ({
      marca,
      modelos: modelos.sort((a, b) => alfabetico(a.modelo, b.modelo)),
    }))
    .sort((a, b) => alfabetico(a.marca, b.marca));
}
