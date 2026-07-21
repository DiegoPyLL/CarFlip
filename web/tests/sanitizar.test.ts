import { describe, expect, it } from 'vitest';

import { escaparHtml, normalizar, normalizarTelefonoCL } from '../src/lib/sanitizar';

describe('normalizar', () => {
  it('colapsa espacios y recorta al máximo indicado', () => {
    expect(normalizar('  Ana   María  ', { max: 100 })).toBe('Ana María');
    expect(normalizar('abcdef', { max: 3 })).toBe('abc');
  });

  it('elimina caracteres de control invisibles', () => {
    // Se arman en código: escritos como literales serían invisibles al leer el test.
    const nulo = String.fromCharCode(0);
    const campana = String.fromCharCode(7);
    expect(normalizar(`Ana${nulo}${campana}María`, { max: 100 })).toBe('AnaMaría');
  });

  it('aplana los saltos de línea salvo que se pidan preservar', () => {
    expect(normalizar('hola\nchao', { max: 100 })).toBe('hola chao');
    expect(normalizar('hola\r\nchao', { max: 100, preservarSaltos: true })).toBe('hola\nchao');
  });

  it('reduce tres o más saltos seguidos a un párrafo', () => {
    expect(normalizar('a\n\n\n\nb', { max: 100, preservarSaltos: true })).toBe('a\n\nb');
  });

  it('devuelve cadena vacía para null', () => {
    expect(normalizar(null, { max: 100 })).toBe('');
  });
});

describe('escaparHtml', () => {
  it('escapa los cinco caracteres con significado en HTML', () => {
    expect(escaparHtml('<script>alert("x")</script>')).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;',
    );
    expect(escaparHtml("O'Higgins & Cía")).toBe('O&#39;Higgins &amp; Cía');
  });

  it('escapa el ampersand antes que el resto, sin doble escape', () => {
    expect(escaparHtml('&lt;')).toBe('&amp;lt;');
  });
});

describe('normalizarTelefonoCL', () => {
  it('acepta las formas habituales de un móvil chileno', () => {
    for (const entrada of ['912345678', '+56912345678', '56 9 1234 5678', '+56 9 1234-5678']) {
      expect(normalizarTelefonoCL(entrada)).toBe('+56 9 12345678');
    }
  });

  it('rechaza fijos, números incompletos y basura', () => {
    for (const entrada of ['221234567', '12345678', '9123456789', 'no soy un teléfono', '', null]) {
      expect(normalizarTelefonoCL(entrada)).toBeNull();
    }
  });
});
