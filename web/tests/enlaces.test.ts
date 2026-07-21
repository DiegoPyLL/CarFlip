import { describe, expect, it } from 'vitest';

import { enlaceAviso } from '../src/lib/enlaces';
import { FUENTES } from '../src/lib/db/fuentes';

describe('enlaceAviso', () => {
  it('manda los particulares a su propia ruta', () => {
    expect(enlaceAviso({ id: 12, fuente: 'particular' })).toBe('/auto/p/12');
  });

  it('manda las cuatro fuentes scrapeadas a /auto/[id]', () => {
    for (const fuente of FUENTES.filter((f) => f !== 'particular')) {
      expect(enlaceAviso({ id: 12, fuente })).toBe('/auto/12');
    }
  });

  it('cubre las cinco fuentes sin repetir destino por id', () => {
    const destinos = new Set(FUENTES.map((fuente) => enlaceAviso({ id: 12, fuente })));
    expect(FUENTES).toHaveLength(5);
    // Un mismo id existe en dos tablas: las rutas tienen que poder distinguirlo.
    expect(destinos).toEqual(new Set(['/auto/12', '/auto/p/12']));
  });

  it('adjunta el destino de vuelta codificado', () => {
    expect(enlaceAviso({ id: 7, fuente: 'yapo' }, '/avisos?marca=Kia&pagina=2')).toBe(
      '/auto/7?back=%2Favisos%3Fmarca%3DKia%26pagina%3D2',
    );
  });

  it('omite el parámetro si no hay a dónde volver', () => {
    expect(enlaceAviso({ id: 7, fuente: 'yapo' })).toBe('/auto/7');
  });
});
