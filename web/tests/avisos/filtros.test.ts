import { describe, expect, it } from 'vitest';

import { FUENTES } from '../../src/lib/db/fuentes';
import { parsearFiltrosDeals, parsearFiltrosUrl } from '../../src/lib/filtros';

const filtrosDe = (query: string) => parsearFiltrosUrl(new URLSearchParams(query));
const dealsDe = (query: string) => parsearFiltrosDeals(new URLSearchParams(query));

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

describe('parsearFiltrosUrl — región, transmisión y tracción', () => {
  it('acepta los valores de las listas cerradas, con acento incluido', () => {
    expect(filtrosDe('region=Metropolitana').region).toBe('Metropolitana');
    expect(filtrosDe(`region=${encodeURIComponent("O'Higgins")}`).region).toBe("O'Higgins");
    expect(filtrosDe(`transmision=${encodeURIComponent('Automática')}`).transmision).toBe('Automática');
    expect(filtrosDe('traccion=4x4').traccion).toBe('4x4');
  });

  it('descarta cualquier valor fuera de la lista', () => {
    // Sin whitelist estos irían a un ilike/eq contra la BD.
    expect(filtrosDe('region=DROP TABLE').region).toBeUndefined();
    expect(filtrosDe('region=metropolitana').region).toBeUndefined(); // sensible a mayúsculas
    expect(filtrosDe('transmision=Automatica').transmision).toBeUndefined(); // sin tilde no es el valor guardado
    expect(filtrosDe('traccion=4x2').traccion).toBeUndefined(); // 4x2 no dice qué eje
    expect(filtrosDe('region=&transmision=&traccion=').region).toBeUndefined();
  });

  it('no deja la clave presente cuando el valor no valida', () => {
    // `undefined` explícito llegaría a la query como filtro activo.
    expect('region' in filtrosDe('region=inventada')).toBe(false);
  });
});

describe('parsearFiltrosUrl — campos numéricos', () => {
  it('entiende un monto con los puntos de miles que muestra el formulario', () => {
    // El `parseFloat` anterior leía "1.500.000" como 1,5 y el filtro se perdía
    // en silencio: pasaba con cualquier URL compartida o editada a mano.
    expect(filtrosDe('precio_min=1.500.000').precio_min).toBe(1500000);
    expect(filtrosDe('precio_max=12.000.000').precio_max).toBe(12000000);
    expect(filtrosDe('km_max=150.000').km_max).toBe(150000);
  });

  it('sigue aceptando el número plano que envía el formulario', () => {
    expect(filtrosDe('precio_min=1500000&km_max=150000')).toMatchObject({
      precio_min: 1500000,
      km_max: 150000,
    });
  });

  it('descarta lo que no es un entero en vez de quedarse con un prefijo', () => {
    // parseFloat('12abc') daba 12; ahora el filtro simplemente no se aplica.
    for (const query of ['precio_max=12abc', 'precio_max=sajhdgdsa', 'precio_max=-5', 'precio_max=1,5']) {
      expect('precio_max' in filtrosDe(query)).toBe(false);
    }
    expect('km_max' in filtrosDe('km_max=-1')).toBe(false);
  });

  it('mantiene el año dentro del rango y la página en 1 por defecto', () => {
    expect(filtrosDe('anio=2018').anio).toBe(2018);
    expect('anio' in filtrosDe('anio=1800')).toBe(false);
    expect(filtrosDe('pagina=abc').pagina).toBe(1);
    expect(filtrosDe('pagina=3').pagina).toBe(3);
  });
});

describe('parsearFiltrosDeals', () => {
  it('hereda los campos base del listado', () => {
    const filtros = dealsDe('marca=Toyota&anio=2018&region=Metropolitana&traccion=4x4');
    expect(filtros).toMatchObject({
      marca: 'Toyota',
      anio: 2018,
      region: 'Metropolitana',
      traccion: '4x4',
    });
  });

  it('acepta categoría y puntaje mínimo, propios de deals', () => {
    expect(dealsDe('categoria=oportunidad_clara').categoria).toBe('oportunidad_clara');
    expect(dealsDe('puntaje_min=80').puntaje_min).toBe(80);
  });

  it('rechaza "descartar": esos deals no se muestran nunca', () => {
    expect(dealsDe('categoria=descartar').categoria).toBeUndefined();
    expect(dealsDe('categoria=inventada').categoria).toBeUndefined();
  });

  it('descarta un puntaje fuera de 1-100', () => {
    expect(dealsDe('puntaje_min=0').puntaje_min).toBeUndefined();
    expect(dealsDe('puntaje_min=101').puntaje_min).toBeUndefined();
    expect(dealsDe('puntaje_min=abc').puntaje_min).toBeUndefined();
  });

  it('ignora el orden: el ranking lo fija el algoritmo', () => {
    expect('orden' in dealsDe('orden=precio_asc')).toBe(false);
  });
});
