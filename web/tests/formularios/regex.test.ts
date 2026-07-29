import { describe, expect, it } from 'vitest';

import { PATRON, RE } from '../../src/lib/regex';

/**
 * El valor del archivo es que el `pattern` del navegador y la validación del
 * servidor salgan de la misma fuente. Estos tests fijan las dos mitades: que
 * cada forma acepte y rechace lo que corresponde, y que anclar `PATRON` a mano
 * —lo que hace el navegador con el atributo— dé exactamente `RE`.
 */

describe('RE.patente', () => {
  it('acepta las cuatro series vigentes', () => {
    // Auto desde 2007, auto anterior, moto desde 2007, moto anterior.
    for (const patente of ['GSBB20', 'AA1000', 'BJH61', 'AA123']) {
      expect(RE.patente.test(patente)).toBe(true);
    }
  });

  it('acepta minúsculas: es lo que se tipea, y el servidor canoniza antes', () => {
    expect(RE.patente.test('gsbb20')).toBe(true);
  });

  it('rechaza vocales y M/N/Q en la serie de cuatro letras', () => {
    for (const patente of ['GSAB20', 'GSMB20', 'GSQB20']) {
      expect(RE.patente.test(patente)).toBe(false);
    }
  });

  it('rechaza separadores, largos que no existen y basura', () => {
    for (const patente of ['GS·BB·20', 'GS-BB-20', 'GSBB2', 'GSBB200', '', 'AAAAAA']) {
      expect(RE.patente.test(patente)).toBe(false);
    }
  });
});

describe('RE.nombre', () => {
  it('acepta letras de cualquier alfabeto y espacios', () => {
    for (const nombre of ['Diego', 'José Ñuñoa', 'Ana María', 'Иван']) {
      expect(RE.nombre.test(nombre)).toBe(true);
    }
  });

  it('rechaza dígitos, signos y el vacío', () => {
    for (const nombre of ['Diego 2', 'Diego<script>', 'Diego@casa', '']) {
      expect(RE.nombre.test(nombre)).toBe(false);
    }
  });
});

describe('RE.email', () => {
  it('acepta la forma mínima y rechaza lo que no la tiene', () => {
    expect(RE.email.test('a@b.cl')).toBe(true);
    expect(RE.email.test('diego.pl+etiqueta@carflip.cl')).toBe(true);
    for (const email of ['a@b', 'a b@c.cl', '@b.cl', 'a@.cl', '']) {
      expect(RE.email.test(email)).toBe(false);
    }
  });
});

describe('RE.movilCL', () => {
  it('acepta el nacional ya limpio y rechaza cualquier otro largo', () => {
    expect(RE.movilCL.test('912345678')).toBe(true);
    expect(RE.movilCL.test('812345678')).toBe(false);
    expect(RE.movilCL.test('91234567')).toBe(false);
    expect(RE.movilCL.test('9123456789')).toBe(false);
  });
});

describe('PATRON y RE describen lo mismo', () => {
  // El navegador ancla el atributo `pattern` por su cuenta: si estas dos
  // versiones divergieran, el formulario aceptaría en el cliente algo que el
  // servidor rechaza después, perdiendo lo tipeado en el POST.
  const pares = [
    ['patente', PATRON.patente, RE.patente, ['GSBB20', 'AA123', 'GSAB20', 'GS·BB·20', '']],
    ['nombre', PATRON.nombre, RE.nombre, ['Diego', 'José Ñuñoa', 'Diego 2', '']],
    ['email', PATRON.email, RE.email, ['a@b.cl', 'a@b', '']],
    ['entero', PATRON.entero, RE.entero, ['0', '1500000', '1.500.000', '-1', '']],
  ] as const;

  for (const [nombre, fuente, compilada, casos] of pares) {
    it(`${nombre}: el atributo anclado coincide con la expresión del servidor`, () => {
      const comoNavegador = new RegExp(`^(?:${fuente})$`, 'u');
      for (const caso of casos) {
        expect(comoNavegador.test(caso)).toBe(compilada.test(caso));
      }
    });
  }
});
