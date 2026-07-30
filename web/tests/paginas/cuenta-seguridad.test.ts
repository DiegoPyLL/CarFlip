import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { describe, expect, it } from 'vitest';

import Seguridad from '../../src/pages/cuenta/seguridad.astro';

/**
 * `/cuenta/seguridad` renderizada de verdad. Lo que se comprueba no es el
 * maquetado sino tres cosas que sí se pueden romper en silencio: que la
 * dirección en curso salga de la sesión, que un cambio a medias tenga salida, y
 * que la querystring —que la escribe cualquiera— no llegue nunca al HTML.
 */

const ORIGIN = 'https://carflip.cl';
const ACTUAL = 'ana@carflip.cl';
const NUEVO = 'ana.nueva@carflip.cl';

const USUARIO = {
  id: 'b3f1c2d4-0000-4000-8000-000000000001',
  email: ACTUAL,
  emailConfirmado: true,
  emailPendiente: '',
  rol: 'usuario' as const,
};

async function renderizar(busqueda = '', usuario: unknown = USUARIO) {
  const contenedor = await AstroContainer.create();
  const respuesta = await contenedor.renderToResponse(Seguridad as never, {
    request: new Request(`${ORIGIN}/cuenta/seguridad${busqueda}`),
    locals: { nonce: 'x', supabase: {}, usuario } as never,
  });
  return { respuesta, html: respuesta.status === 200 ? await respuesta.text() : '' };
}

describe('/cuenta/seguridad', () => {
  it('sin cambio en curso pide una dirección nueva y nada más', async () => {
    const { html } = await renderizar();

    expect(html).toContain('name="email"');
    expect(html).not.toContain('name="codigo_actual"');
    expect(html).not.toContain('name="codigo_nuevo"');
    // El nonce solo aparece si el servidor lo pidió: con sesión reciente el
    // cambio de contraseña no tiene paso extra.
    expect(html).not.toContain('name="nonce"');
  });

  it('con cambio en curso pide los dos códigos y nombra las dos direcciones', async () => {
    const { html } = await renderizar('', { ...USUARIO, emailPendiente: NUEVO });

    expect(html).toContain('name="codigo_actual"');
    expect(html).toContain('name="codigo_nuevo"');
    expect(html).toContain(ACTUAL);
    expect(html).toContain(NUEVO);
  });

  it('deja salida a un cambio pendiente hacia una dirección mal tecleada', async () => {
    // Sin el formulario de cambio a la vista, un typo en la dirección dejaba la
    // cuenta con un cambio que nunca podía completarse ni corregirse.
    const { html } = await renderizar('', { ...USUARIO, emailPendiente: NUEVO });
    expect(html).toContain('name="email"');
    expect(html).toContain('Escribe otra dirección');
  });

  it('la dirección en curso sale de la sesión, no de la querystring', async () => {
    const { html } = await renderizar('?correo=atacante@evil.com&estado=correo_enviado');

    expect(html).not.toContain('atacante@evil.com');
    expect(html).not.toContain('name="codigo_actual"');
  });

  it('revela el campo del nonce solo cuando el servidor lo pidió', async () => {
    for (const busqueda of ['?error=reautenticar', '?error=nonce_invalido', '?estado=nonce_enviado']) {
      const { html } = await renderizar(busqueda);
      expect(html).toContain('name="nonce"');
    }

    const { html } = await renderizar('?estado=correo_guardado');
    expect(html).not.toContain('name="nonce"');
  });

  it('no refleja en el HTML el código de error que venga por la URL', async () => {
    // El catálogo de `seguridad.ts` es lo que impide que esto sea un hueco de
    // inyección: cualquier valor ajeno cae en el mensaje genérico.
    const { html } = await renderizar('?error=<img src=x onerror=alert(1)>');

    expect(html).not.toContain('onerror');
    expect(html).toContain('No pudimos completar la operación.');
  });

  it('ignora un estado de éxito inventado en vez de mostrar algo', async () => {
    const { html } = await renderizar('?estado=cuenta_regalada');
    expect(html).not.toContain('cuenta_regalada');
    expect(html).not.toContain('role="status"');
  });

  it('sin sesión redirige a entrar en vez de renderizar la página', async () => {
    const { respuesta } = await renderizar('', null);
    expect(respuesta.status).toBe(302);
    expect(respuesta.headers.get('location')).toBe('/entrar?volver=/cuenta/seguridad');
  });
});
