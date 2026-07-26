import { describe, expect, it } from 'vitest';

import { formatearPatente, normalizarPatente } from '@lib/patente';

describe('normalizarPatente', () => {
  it('acepta los cuatro formatos vigentes', () => {
    expect(normalizarPatente('GSBB20')).toBe('GSBB20'); // auto desde 2007
    expect(normalizarPatente('AA1000')).toBe('AA1000'); // auto anterior
    expect(normalizarPatente('BJH61')).toBe('BJH61'); // moto desde 2007
    expect(normalizarPatente('AA123')).toBe('AA123'); // moto anterior
  });

  it('canoniza minúsculas y separadores', () => {
    expect(normalizarPatente('gs·bb·20')).toBe('GSBB20');
    expect(normalizarPatente('gs-bb-20')).toBe('GSBB20');
    expect(normalizarPatente('bjh 61')).toBe('BJH61');
    expect(normalizarPatente('aa.1000')).toBe('AA1000');
  });

  it('rechaza vocales y M, N, Q en la serie desde 2007', () => {
    expect(normalizarPatente('ABAB12')).toBeNull();
    expect(normalizarPatente('MNPQ12')).toBeNull();
    expect(normalizarPatente('AEI61')).toBeNull();
  });

  it('rechaza largos y estructuras inválidas', () => {
    expect(normalizarPatente('GSBB2')).toBeNull(); // 4 letras + 1 dígito
    expect(normalizarPatente('GSBB200')).toBeNull(); // 7 caracteres
    expect(normalizarPatente('123456')).toBeNull(); // sin letras
    expect(normalizarPatente('GSBBCC')).toBeNull(); // sin dígitos
    expect(normalizarPatente('A1000')).toBeNull(); // 1 letra
    expect(normalizarPatente('1000AA')).toBeNull(); // orden invertido
    expect(normalizarPatente('')).toBeNull();
    expect(normalizarPatente(null)).toBeNull();
  });
});

describe('formatearPatente', () => {
  it('agrupa autos en pares y motos en letras·dígitos', () => {
    expect(formatearPatente('GSBB20')).toBe('GS·BB·20');
    expect(formatearPatente('AA1000')).toBe('AA·10·00');
    expect(formatearPatente('BJH61')).toBe('BJH·61');
    expect(formatearPatente('AA123')).toBe('AA·123');
  });
});
