import { describe, expect, it } from 'vitest';

import { enlaceAviso, parsearRefAviso } from '../../src/lib/enlaces';
import { FUENTES, FUENTES_SCRAPEADAS } from '../../src/lib/db/fuentes';

describe('enlaceAviso', () => {
  it('manda los particulares a su propia ruta', () => {
    expect(enlaceAviso({ id: 12, fuente: 'particular' })).toBe('/auto/p/12');
  });

  it('lleva la fuente en la ruta de cada aviso scrapeado', () => {
    expect(enlaceAviso({ id: 12, fuente: 'yapo' })).toBe('/auto/yapo-12');
    expect(enlaceAviso({ id: 12, fuente: 'autocosmos' })).toBe('/auto/autocosmos-12');
  });

  it('cubre las cinco fuentes sin repetir destino por id', () => {
    const destinos = new Set(FUENTES.map((fuente) => enlaceAviso({ id: 12, fuente })));
    expect(FUENTES).toHaveLength(5);
    // El mismo id existe en las cinco tablas: cinco fuentes, cinco URLs distintas.
    expect(destinos.size).toBe(FUENTES.length);
  });

  it('adjunta el destino de vuelta codificado', () => {
    expect(enlaceAviso({ id: 7, fuente: 'yapo' }, '/avisos?marca=Kia&pagina=2')).toBe(
      '/auto/yapo-7?back=%2Favisos%3Fmarca%3DKia%26pagina%3D2',
    );
  });

  it('omite el parámetro si no hay a dónde volver', () => {
    expect(enlaceAviso({ id: 7, fuente: 'yapo' })).toBe('/auto/yapo-7');
  });
});

describe('parsearRefAviso', () => {
  it('recupera el par que emitió enlaceAviso', () => {
    for (const fuente of FUENTES_SCRAPEADAS) {
      const ruta = enlaceAviso({ id: 757, fuente });
      expect(parsearRefAviso(ruta.replace('/auto/', ''))).toEqual({ fuente, id: 757 });
    }
  });

  it('rechaza el id sin fuente', () => {
    expect(parsearRefAviso('757')).toBeNull();
  });

  it('rechaza a los particulares, que tienen su propia ruta', () => {
    expect(parsearRefAviso('particular-12')).toBeNull();
    expect(parsearRefAviso('p-12')).toBeNull();
  });

  it('rechaza cualquier otra cosa', () => {
    for (const basura of ['basura', 'yapo-', '-12', 'yapo-abc', 'yapo-12-3', '']) {
      expect(parsearRefAviso(basura)).toBeNull();
    }
  });
});
