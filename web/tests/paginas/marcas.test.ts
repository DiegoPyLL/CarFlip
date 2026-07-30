import { describe, expect, it } from 'vitest';

import { agruparMarcas } from '@lib/marcas';

/**
 * `agruparMarcas` decide qué páginas de marca existen: la consumen el hub
 * /marcas y sitemap-marcas.xml. Un slug mal formado acá es una URL enlazada y
 * declarada en el sitemap que responde 404, así que lo que se prueba es la
 * entrada sucia —grafías mezcladas, precios basura, nombres con caracteres de
 * URL—, no el caso limpio.
 */

const fila = (marca: string | null, precio: string | null = null) => ({ marca, precio });
const porSlug = (filas: Parameters<typeof agruparMarcas>[0], slug: string) =>
  agruparMarcas(filas).find((m) => m.slug === slug);

describe('agruparMarcas — normalización del slug', () => {
  it('colapsa las grafías de una misma marca en un solo slug', () => {
    const marcas = agruparMarcas([fila('Kia'), fila('KIA'), fila('kia'), fila('kIa')]);

    // Cuatro grafías, una sola página: el `ilike` de /marcas/{marca} no las
    // distingue, así que listarlas por separado serían cuatro URLs idénticas.
    expect(marcas).toHaveLength(1);
    expect(marcas[0].slug).toBe('kia');
    expect(marcas[0].total).toBe(4);
  });

  it('muestra la primera grafía vista, no el slug', () => {
    // La página de marca hace lo mismo (`obtenerDatosMarca`), y el hub tiene que
    // llamarla igual o el visitante ve dos nombres para el mismo auto.
    expect(agruparMarcas([fila('Kia'), fila('KIA')])[0].nombre).toBe('Kia');
    expect(agruparMarcas([fila('KIA'), fila('Kia')])[0].nombre).toBe('KIA');
  });

  it('no recorta los espacios del slug', () => {
    // Recortar produciría el enlace /marcas/kia, y el `ilike('marca', 'kia')` de
    // la página no encuentra la fila " Kia ": el hub enlazaría a un 404.
    expect(agruparMarcas([fila(' Kia ')])[0].slug).toBe(' kia ');
  });

  it('descarta las filas sin marca en vez de inventar una entrada vacía', () => {
    expect(agruparMarcas([fila(null), fila(null)])).toEqual([]);
    expect(agruparMarcas([fila(null), fila('Kia')])).toHaveLength(1);
  });

  it('trata la cadena vacía como ausencia de marca', () => {
    // Un slug vacío daría la URL /marcas/, que no es la página de ninguna marca.
    expect(agruparMarcas([fila('')])).toEqual([]);
  });

  it('mantiene distintas dos marcas que solo se parecen', () => {
    const marcas = agruparMarcas([fila('Mini'), fila('MINI Cooper')]);

    expect(marcas.map((m) => m.slug).sort()).toEqual(['mini', 'mini cooper']);
  });
});

describe('agruparMarcas — precios sucios', () => {
  it('ignora los precios que no son un número', () => {
    const kia = porSlug([fila('Kia', 'abc'), fila('Kia', '5000000')], 'kia');

    expect(kia?.precio_minimo).toBe(5_000_000);
    expect(kia?.precio_maximo).toBe(5_000_000);
    // El aviso sigue contando: no tener precio válido no lo saca del catálogo.
    expect(kia?.total).toBe(2);
  });

  it('ignora el cero y los negativos, que no son un precio de venta', () => {
    const kia = porSlug([fila('Kia', '0'), fila('Kia', '-1'), fila('Kia', '7000000')], 'kia');

    expect(kia?.precio_minimo).toBe(7_000_000);
    expect(kia?.precio_maximo).toBe(7_000_000);
  });

  it('devuelve el rango en null cuando ningún precio sirve, sin romperse', () => {
    // `Math.min()` sin argumentos devuelve Infinity, que se pintaría como un
    // precio real en la tarjeta del hub.
    const kia = porSlug([fila('Kia', null), fila('Kia', 'null'), fila('Kia', '0')], 'kia');

    expect(kia?.precio_minimo).toBeNull();
    expect(kia?.precio_maximo).toBeNull();
    expect(kia?.total).toBe(3);
  });

  it('toma el mínimo y el máximo reales, no el primero y el último', () => {
    const kia = porSlug(
      [fila('Kia', '9000000'), fila('Kia', '3000000'), fila('Kia', '20000000'), fila('Kia', '5000000')],
      'kia',
    );

    expect(kia?.precio_minimo).toBe(3_000_000);
    expect(kia?.precio_maximo).toBe(20_000_000);
  });

  it('acepta los decimales con los que Postgres serializa numeric', () => {
    const kia = porSlug([fila('Kia', '5000000.00')], 'kia');

    expect(kia?.precio_minimo).toBe(5_000_000);
  });
});

describe('agruparMarcas — la URL que produce', () => {
  it('sobrevive a los caracteres que parten una ruta', () => {
    const filas = [fila('Rolls/Royce'), fila('100% Autos'), fila('Mercedes & Co'), fila('Citroën')];

    for (const { slug } of agruparMarcas(filas)) {
      const ruta = `/marcas/${encodeURIComponent(slug)}`;
      // Un `/` sin codificar añadiría un segmento y la ruta dejaría de existir;
      // un `%` suelto rompe el `decodeURIComponent` de la página.
      expect(ruta.split('/')).toHaveLength(3);
      expect(decodeURIComponent(ruta.slice('/marcas/'.length))).toBe(slug);
    }
  });

  it('conserva los acentos en minúscula sin descomponerlos', () => {
    expect(agruparMarcas([fila('Citroën')])[0].slug).toBe('citroën');
  });
});

describe('agruparMarcas — orden', () => {
  it('ordena de mayor a menor cantidad de avisos', () => {
    const marcas = agruparMarcas([
      fila('Suzuki'),
      fila('Kia'),
      fila('Kia'),
      fila('Toyota'),
      fila('Toyota'),
      fila('Toyota'),
    ]);

    expect(marcas.map((m) => m.slug)).toEqual(['toyota', 'kia', 'suzuki']);
  });

  it('devuelve una lista vacía sin filas, no un error', () => {
    expect(agruparMarcas([])).toEqual([]);
  });
});
