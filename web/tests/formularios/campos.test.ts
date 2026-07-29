import { describe, expect, it } from 'vitest';

import {
  aEntero,
  digitos,
  miles,
  montoCLP,
  tecleoPatente,
  tecleoTelefonoCL,
  textoLimpio,
} from '../../src/lib/campos';

describe('digitos', () => {
  it('descarta todo lo que no sea dígito y recorta al tope', () => {
    expect(digitos('sajhdgdsa', 9)).toBe('');
    expect(digitos('1a2b3c', 9)).toBe('123');
    expect(digitos('812981739237', 9)).toBe('812981739');
  });
});

describe('miles y montoCLP', () => {
  it('agrupan de a tres con el punto chileno', () => {
    expect(miles('1500000', 9)).toBe('1.500.000');
    expect(montoCLP('1500000', 9)).toBe('$1.500.000');
  });

  it('devuelven vacío cuando no queda ningún dígito', () => {
    // El caso de la issue: un campo de precio con letras no debe conservarlas.
    expect(montoCLP('sajhdgdsa', 9)).toBe('');
    expect(miles('', 7)).toBe('');
  });

  it('no arrastran ceros a la izquierda', () => {
    expect(miles('000150', 7)).toBe('150');
  });

  it('son idempotentes: reformatear un valor ya formateado no lo cambia', () => {
    expect(montoCLP(montoCLP('1500000', 9), 9)).toBe('$1.500.000');
    expect(miles(miles('150000', 7), 7)).toBe('150.000');
  });
});

describe('aEntero', () => {
  it('lee un monto con puntos de miles, que es donde parseFloat fallaba', () => {
    // parseFloat('1.500.000') devuelve 1.5: el filtro por precio se perdía.
    expect(aEntero('1.500.000')).toBe(1500000);
    expect(aEntero('$1.500.000')).toBeNull();
    expect(aEntero('1500000')).toBe(1500000);
    expect(aEntero(' 150 000 ')).toBe(150000);
  });

  it('rechaza lo que no es un entero', () => {
    for (const valor of ['', 'abc', '-1', '1,5', '1e6', null, undefined]) {
      expect(aEntero(valor)).toBeNull();
    }
  });

  it('rechaza lo que no cabe en un entero seguro', () => {
    expect(aEntero('9'.repeat(20))).toBeNull();
  });
});

describe('tecleoPatente', () => {
  it('canoniza lo que se va escribiendo', () => {
    expect(tecleoPatente('gsbb20')).toBe('GSBB20');
    expect(tecleoPatente('gs-bb 20')).toBe('GSBB20');
    expect(tecleoPatente('GS·BB·20')).toBe('GSBB20');
  });

  it('acepta el valor a medio escribir y corta en 6', () => {
    expect(tecleoPatente('gs')).toBe('GS');
    expect(tecleoPatente('GSBB2099')).toBe('GSBB20');
  });
});

describe('tecleoTelefonoCL', () => {
  it('enmascara a la forma canónica desde cualquier entrada', () => {
    expect(tecleoTelefonoCL('912345678')).toBe('+56 9 1234 5678');
    expect(tecleoTelefonoCL('56912345678')).toBe('+56 9 1234 5678');
    expect(tecleoTelefonoCL('+56 9 1234 5678')).toBe('+56 9 1234 5678');
  });

  it('acompaña el tipeo en vez de borrar lo escrito', () => {
    expect(tecleoTelefonoCL('')).toBe('');
    expect(tecleoTelefonoCL('9')).toBe('+56 9');
    expect(tecleoTelefonoCL('912')).toBe('+56 9 12');
    expect(tecleoTelefonoCL('91234567890')).toBe('+56 9 1234 5678');
  });

  it('es idempotente: reformatear el resultado no lo altera', () => {
    expect(tecleoTelefonoCL(tecleoTelefonoCL('912345678'))).toBe('+56 9 1234 5678');
    expect(tecleoTelefonoCL(tecleoTelefonoCL('912'))).toBe('+56 9 12');
  });
});

describe('textoLimpio', () => {
  it('colapsa espacios y recorta los extremos', () => {
    expect(textoLimpio('  toyota   corolla  ')).toBe('toyota corolla');
    expect(textoLimpio('\tcorolla\n')).toBe('corolla');
    expect(textoLimpio('   ')).toBe('');
  });
});
