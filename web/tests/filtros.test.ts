import { describe, expect, it } from 'vitest';

import { FUENTES } from '../src/lib/db/fuentes';
import { parsearFiltrosUrl } from '../src/lib/filtros';

const filtrosDe = (query: string) => parsearFiltrosUrl(new URLSearchParams(query));

describe('parsearFiltrosUrl — fuente', () => {
  it('acepta las cinco fuentes, particulares incluidos', () => {
    for (const fuente of FUENTES) {
      expect(filtrosDe(`fuente=${fuente}`).fuente).toBe(fuente);
    }
  });

  it('descarta una fuente inválida en vez de pasarla a la consulta', () => {
    expect(filtrosDe('fuente=perfiles').fuente).toBeUndefined();
    expect(filtrosDe('fuente=').fuente).toBeUndefined();
    expect(filtrosDe('fuente=PARTICULAR').fuente).toBeUndefined();
    expect(filtrosDe("fuente=particular';drop").fuente).toBeUndefined();
  });

  it('deja el resto de los filtros intacto', () => {
    const filtros = filtrosDe('fuente=particular&marca=Toyota&anio=2018&orden=precio_asc');
    expect(filtros).toMatchObject({
      fuente: 'particular',
      marca: 'Toyota',
      anio: 2018,
      orden: 'precio_asc',
      pagina: 1,
    });
  });
});
