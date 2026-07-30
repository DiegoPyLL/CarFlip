import { describe, expect, it } from 'vitest';

import { enlaceAviso } from '../../src/lib/enlaces';
import { FUENTES, TABLA_POR_FUENTE } from '../../src/lib/db/fuentes';

describe('enlaceAviso', () => {
  it('manda los avisos a la ruta de particulares', () => {
    expect(enlaceAviso({ id: 12 })).toBe('/auto/p/12');
  });

  it('adjunta el destino de vuelta codificado', () => {
    expect(enlaceAviso({ id: 7 }, '/avisos?marca=Kia&pagina=2')).toBe(
      '/auto/p/7?back=%2Favisos%3Fmarca%3DKia%26pagina%3D2',
    );
  });

  it('omite el parámetro si no hay a dónde volver', () => {
    expect(enlaceAviso({ id: 7 })).toBe('/auto/p/7');
  });
});

describe('fuentes', () => {
  it('declara una sola fuente y su tabla', () => {
    expect(FUENTES).toEqual(['particular']);
    expect(TABLA_POR_FUENTE.particular).toBe('particulares_listings');
  });
});
