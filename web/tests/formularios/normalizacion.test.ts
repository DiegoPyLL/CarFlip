import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { describe, expect, it } from 'vitest';

import CampoNumero from '../../src/components/filtros/CampoNumero.astro';
import FormularioAviso from '../../src/components/cuenta/FormularioAviso.astro';
import { KM_MAXIMO, PRECIO_MAXIMO } from '../../src/lib/publicaciones/opciones';
import { PATRON } from '../../src/lib/regex';

/**
 * El contrato entre el marcado y el script de `Normalizacion`: este busca
 * `input[data-normaliza]` y lee `data-max`/`data-rango`. Si un campo pierde su
 * atributo deja de normalizarse sin que nada falle a la vista, así que se fija
 * acá —el formulario de aviso además vive tras sesión y no se puede pedir por
 * HTTP en una prueba.
 */

const render = async (componente: Parameters<AstroContainer['renderToString']>[0], props = {}) => {
  const contenedor = await AstroContainer.create();
  return contenedor.renderToString(componente, { props });
};

const atributosDe = (html: string, nombre: string) =>
  html.match(new RegExp(`<input[^>]*name="${nombre}"[^>]*>`))?.[0] ?? '';

describe('CampoNumero', () => {
  it('emite un campo de texto formateable, no un type=number', () => {
    // Un `type="number"` declara inválido "1.500.000" y descarta lo tipeado.
    return render(CampoNumero, { tipo: 'precio', nombre: 'precio_max', etiqueta: 'Precio máximo' }).then((html) => {
      const input = atributosDe(html, 'precio_max');
      expect(input).toContain('type="text"');
      expect(input).toContain('inputmode="numeric"');
      expect(input).toContain('data-normaliza="precio"');
      expect(input).toContain(`pattern="${PATRON.monto}"`);
      expect(input).toContain(`data-max="${PRECIO_MAXIMO}"`);
    });
  });

  it('el campo de kilometraje lleva su propio tope y unidad', async () => {
    const html = await render(CampoNumero, { tipo: 'km', nombre: 'km_max', etiqueta: 'Km máximo' });
    const input = atributosDe(html, 'km_max');
    expect(input).toContain('data-normaliza="km"');
    expect(input).toContain(`data-max="${KM_MAXIMO}"`);
    expect(html).toContain('2.000.000 km');
  });

  it('el mensaje de rango es el mismo bajo el campo y en data-rango', async () => {
    const html = await render(CampoNumero, { tipo: 'km', nombre: 'km_max', etiqueta: 'Km máximo' });
    const mensaje = atributosDe(html, 'km_max').match(/data-rango="([^"]*)"/)?.[1];
    expect(mensaje).toBeTruthy();
    // El `<p class="campo-error">` es lo que se ve sin JavaScript; `data-rango`
    // lo que `setCustomValidity` dice al pasarse del tope. Deben coincidir.
    const parrafo = html.match(/<p id="err-km_max"[^>]*>([\s\S]*?)<\/p>/)?.[1];
    expect(parrafo?.trim()).toBe(mensaje);
  });

  it('asocia el error al campo para lectores de pantalla', async () => {
    const html = await render(CampoNumero, { tipo: 'precio', nombre: 'precio_min', etiqueta: 'Precio mínimo' });
    expect(atributosDe(html, 'precio_min')).toContain('aria-describedby="err-precio_min"');
    expect(html).toContain('id="err-precio_min"');
  });
});

describe('FormularioAviso', () => {
  it('marca cada campo con el formato que le toca', async () => {
    const html = await render(FormularioAviso, { accion: '/api/publicacion', textoBoton: 'Publicar' });

    expect(atributosDe(html, 'precio')).toContain('data-normaliza="precio"');
    expect(atributosDe(html, 'km')).toContain('data-normaliza="km"');
    expect(atributosDe(html, 'patente')).toContain('data-normaliza="patente"');
    for (const campo of ['marca', 'modelo', 'version']) {
      expect(atributosDe(html, campo)).toContain('data-normaliza="texto"');
    }
  });

  it('precio y km dejaron de ser type=number, que impedía los puntos', async () => {
    const html = await render(FormularioAviso, { accion: '/api/publicacion', textoBoton: 'Publicar' });
    for (const campo of ['precio', 'km']) {
      expect(atributosDe(html, campo)).toContain('type="text"');
      expect(atributosDe(html, campo)).not.toContain('type="number"');
    }
    // Ya no se le pide al usuario escribir el monto "sin puntos".
    expect(html).not.toContain('sin puntos.');
  });

  it('la patente usa el mismo patrón del que el servidor deriva el suyo', async () => {
    const html = await render(FormularioAviso, { accion: '/api/publicacion', textoBoton: 'Publicar' });
    expect(atributosDe(html, 'patente')).toContain(`pattern="${PATRON.patente}"`);
  });

  it('los topes del navegador son los mismos que valida el servidor', async () => {
    const html = await render(FormularioAviso, { accion: '/api/publicacion', textoBoton: 'Publicar' });
    expect(atributosDe(html, 'km')).toContain(`data-max="${KM_MAXIMO}"`);
    expect(atributosDe(html, 'precio')).toContain(`data-max="${PRECIO_MAXIMO}"`);
  });
});
