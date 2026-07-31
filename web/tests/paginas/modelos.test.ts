import { describe, expect, it } from 'vitest';

import { paginasAnio, paginasModelo, slugModelo } from '@lib/marcas';

/**
 * Estas tres funciones deciden qué páginas de modelo y de año existen: las
 * consumen la página —que responde 404 si el modelo no sale acá—, los enlaces de
 * /marcas/{marca} y sitemap-marcas.xml. Un desacuerdo entre ellas es un enlace
 * interno o una entrada de sitemap que responde 404, así que lo que se prueba es
 * la entrada sucia: modelos sin nombre, con separadores raros, con grafías que
 * colapsan, y umbrales en el borde.
 */

const fila = (modelo: string | null, precio: string | null = null, anio: number | null = null) => ({
  modelo,
  precio,
  anio,
});

describe('slugModelo', () => {
  it('baja a minúsculas y une con guion lo que no es letra ni número', () => {
    expect(slugModelo('Yaris')).toBe('yaris');
    expect(slugModelo('CX-5')).toBe('cx-5');
    expect(slugModelo('Serie 3')).toBe('serie-3');
    expect(slugModelo('Golf (mk7)')).toBe('golf-mk7');
    expect(slugModelo('1.6 HDi')).toBe('1-6-hdi');
  });

  it('traduce la barra en vez de dejarla partir la ruta', () => {
    // Sin traducirla, /marcas/audi/a4-2-0/tdi es un segmento de más y la página
    // deja de existir.
    expect(slugModelo('A4 2.0/TDI')).toBe('a4-2-0-tdi');
    expect(`/marcas/audi/${slugModelo('A4 2.0/TDI')}`.split('/')).toHaveLength(4);
  });

  it('conserva los acentos, igual que el slug de marca', () => {
    expect(slugModelo('Citroën C4')).toBe('citroën-c4');
  });

  it('no deja guiones sueltos en los extremos ni repetidos', () => {
    // " Yaris " daría "-yaris-", que es una URL distinta para el mismo modelo.
    expect(slugModelo(' Yaris ')).toBe('yaris');
    expect(slugModelo('Clase  A')).toBe('clase-a');
    expect(slugModelo('--Yaris--')).toBe('yaris');
  });

  it('devuelve cadena vacía cuando no queda nada que nombrar', () => {
    // La página lo trata como 404: /marcas/kia/ no es la página de un modelo.
    expect(slugModelo('---')).toBe('');
    expect(slugModelo('¿?')).toBe('');
    expect(slugModelo('')).toBe('');
  });
});

describe('paginasModelo — qué modelos tienen página', () => {
  const cinco = (nombre: string) => Array.from({ length: 5 }, () => fila(nombre));

  it('deja fuera los modelos que no llegan al mínimo', () => {
    const modelos = paginasModelo([...cinco('Yaris'), fila('Baleno'), fila('Baleno')], 5);

    expect(modelos.map((m) => m.slug)).toEqual(['yaris']);
  });

  it('trata el mínimo como inclusivo', () => {
    // Con 4 no hay página y con 5 sí: el borde tiene que estar en el mismo lugar
    // en la página, en el enlace y en el sitemap.
    expect(paginasModelo(cinco('Yaris').slice(0, 4), 5)).toEqual([]);
    expect(paginasModelo(cinco('Yaris'), 5)).toHaveLength(1);
  });

  it('junta en una página las grafías que colapsan al mismo slug', () => {
    const modelos = paginasModelo([fila('Serie 3'), fila('serie-3'), fila('SERIE 3')], 1);

    expect(modelos).toHaveLength(1);
    expect(modelos[0].slug).toBe('serie-3');
    expect(modelos[0].total).toBe(3);
    // Las tres grafías viajan a la consulta de avisos: buscar solo por la
    // primera dejaría fuera los avisos de las otras dos.
    expect(modelos[0].grafias.sort()).toEqual(['SERIE 3', 'Serie 3', 'serie-3']);
  });

  it('muestra la primera grafía vista, no el slug', () => {
    expect(paginasModelo([fila('CX-5'), fila('cx 5')], 1)[0].nombre).toBe('CX-5');
  });

  it('descarta las filas sin modelo y las que se quedan sin slug', () => {
    expect(paginasModelo([fila(null), fila(''), fila('---')], 1)).toEqual([]);
  });

  it('promedia solo los precios que sirven como precio de venta', () => {
    const modelos = paginasModelo(
      [fila('Yaris', '0'), fila('Yaris', '-1'), fila('Yaris', 'abc'), fila('Yaris', '8000000')],
      1,
    );

    expect(modelos[0].precio_promedio).toBe(8_000_000);
    // Ninguno de los cuatro sale del catálogo por no tener precio válido.
    expect(modelos[0].total).toBe(4);
  });

  it('deja el promedio en null cuando ningún precio sirve', () => {
    expect(paginasModelo([fila('Yaris', null), fila('Yaris', '0')], 1)[0].precio_promedio).toBeNull();
  });

  it('ordena de mayor a menor cantidad de avisos', () => {
    const filas = [...cinco('Yaris'), ...cinco('Corolla'), ...cinco('Corolla')];

    expect(paginasModelo(filas, 1).map((m) => m.slug)).toEqual(['corolla', 'yaris']);
  });

  it('devuelve una lista vacía sin filas, no un error', () => {
    expect(paginasModelo([], 5)).toEqual([]);
  });
});

describe('paginasAnio — qué años tienen página', () => {
  const anios = (anio: number, veces: number) => Array.from({ length: veces }, () => fila('Yaris', null, anio));

  it('deja fuera los años que no llegan al mínimo', () => {
    const resultado = paginasAnio([...anios(2018, 3), ...anios(2019, 2)], 3);

    expect(resultado.map((a) => a.anio)).toEqual([2018]);
  });

  it('no necesita validar el rango del año: solo existen los del catálogo', () => {
    // La página de /marcas/toyota/yaris/99999 responde 404 porque 99999 no sale
    // acá, no porque haya un rango escrito en alguna parte.
    const resultado = paginasAnio(anios(2018, 3), 3);

    expect(resultado.some((a) => a.anio === 99999)).toBe(false);
  });

  it('ignora las filas sin año y el año cero', () => {
    const resultado = paginasAnio([fila('Yaris', null, null), fila('Yaris', null, 0)], 1);

    expect(resultado).toEqual([]);
  });

  it('ordena del año más nuevo al más viejo', () => {
    const filas = [...anios(2015, 1), ...anios(2022, 1), ...anios(2018, 1)];

    expect(paginasAnio(filas, 1).map((a) => a.anio)).toEqual([2022, 2018, 2015]);
  });

  it('promedia el precio de cada año por separado', () => {
    const filas = [
      fila('Yaris', '10000000', 2020),
      fila('Yaris', '12000000', 2020),
      fila('Yaris', '6000000', 2015),
    ];
    const resultado = paginasAnio(filas, 1);

    expect(resultado.find((a) => a.anio === 2020)?.precio_promedio).toBe(11_000_000);
    expect(resultado.find((a) => a.anio === 2015)?.precio_promedio).toBe(6_000_000);
  });
});
