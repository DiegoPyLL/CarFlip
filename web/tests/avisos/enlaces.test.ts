import { describe, expect, it } from 'vitest';

import { enlaceAviso, volverAlListado } from '../../src/lib/enlaces';
import { FUENTES, TABLA_POR_FUENTE } from '../../src/lib/db/fuentes';

const ORIGEN = 'https://carflip.cl';

describe('enlaceAviso', () => {
  it('manda los avisos a la ruta de particulares', () => {
    expect(enlaceAviso({ id: 12 })).toBe('/auto/p/12');
  });

  it('produce una sola URL por aviso, sin parámetros de contexto', () => {
    // El `?back=` que llevaba antes daba una URL distinta por tarjeta: cada
    // listado filtrado multiplicaba las URLs rastreables de la misma ficha.
    expect(enlaceAviso({ id: 7 })).toBe('/auto/p/7');
    expect(enlaceAviso({ id: 7 })).not.toContain('?');
  });
});

/**
 * `volverAlListado` reemplaza a ese `?back=`. Como ahora el destino sale de una
 * cabecera que manda el navegador, lo que importa es que no se pueda usar para
 * mandar a nadie fuera del sitio ni para romper la página.
 */
describe('volverAlListado', () => {
  it('vuelve al listado del que se vino, con sus filtros', () => {
    expect(volverAlListado(`${ORIGEN}/avisos?marca=Kia&pagina=2`, ORIGEN)).toBe('/avisos?marca=Kia&pagina=2');
  });

  it('cae al listado completo sin cabecera', () => {
    expect(volverAlListado(null, ORIGEN)).toBe('/avisos');
    expect(volverAlListado('', ORIGEN)).toBe('/avisos');
  });

  it('no manda fuera del sitio', () => {
    for (const externo of [
      'https://evil.example/avisos',
      'http://carflip.cl.evil.example/avisos',
      'https://carflip.cl.evil.example/avisos',
      // Otro esquema sobre el mismo host tampoco es el mismo origen.
      'http://carflip.cl/avisos',
    ]) {
      expect(volverAlListado(externo, ORIGEN)).toBe('/avisos');
    }
  });

  it('no deja pasar un esquema ejecutable ni una ruta relativa suelta', () => {
    // `new URL` acepta "javascript:..." como URL válida; el origen es "null" y
    // no coincide, así que nunca llega a un href.
    expect(volverAlListado('javascript:alert(1)', ORIGEN)).toBe('/avisos');
    expect(volverAlListado('data:text/html,<script>', ORIGEN)).toBe('/avisos');
    expect(volverAlListado('//evil.example/avisos', ORIGEN)).toBe('/avisos');
    expect(volverAlListado('/avisos', ORIGEN)).toBe('/avisos');
    expect(volverAlListado('no es una url', ORIGEN)).toBe('/avisos');
  });

  it('descarta el hash y conserva la query tal cual', () => {
    expect(volverAlListado(`${ORIGEN}/deals?categoria=buen_precio#lista`, ORIGEN)).toBe(
      '/deals?categoria=buen_precio',
    );
  });

  it('funciona en un origen de preview, no solo en el de producción', () => {
    const preview = 'https://carflip-abc123.vercel.app';

    expect(volverAlListado(`${preview}/avisos?marca=Kia`, preview)).toBe('/avisos?marca=Kia');
    expect(volverAlListado(`${ORIGEN}/avisos`, preview)).toBe('/avisos');
  });
});

describe('fuentes', () => {
  it('declara una sola fuente y su tabla', () => {
    expect(FUENTES).toEqual(['particular']);
    expect(TABLA_POR_FUENTE.particular).toBe('particulares_listings');
  });
});
