import type { APIContext } from 'astro';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import Pagina403 from '../../src/pages/403.astro';
import Pagina404 from '../../src/pages/404.astro';
import Pagina500 from '../../src/pages/500.astro';

// La sesión que devolverá el cliente de Supabase mockeado. Se declara con
// `vi.hoisted` porque `vi.mock` se eleva por sobre los imports y su fábrica no
// puede leer variables del módulo.
const sesion = vi.hoisted(() => ({
  usuario: null as null | { id: string; email: string; app_metadata: { rol?: string } },
}));

vi.mock('@lib/auth/servidor', async (importarOriginal) => ({
  ...(await importarOriginal<typeof import('../../src/lib/auth/servidor')>()),
  AUTH_CONFIGURADA: true,
  tieneCookieSesion: () => sesion.usuario !== null,
  crearClienteUsuario: () => ({
    auth: { getUser: async () => ({ data: { user: sesion.usuario } }) },
  }),
}));

const { onRequest } = await import('../../src/middleware');

const PAGINAS = [
  { codigo: 404, componente: Pagina404, encabezado: 'Esta página ya no está.' },
  { codigo: 403, componente: Pagina403, encabezado: 'No tienes acceso a esta página.' },
  { codigo: 500, componente: Pagina500, encabezado: 'Algo se rompió de nuestro lado.' },
];

async function renderizar(componente: unknown, props?: Record<string, unknown>) {
  const contenedor = await AstroContainer.create();
  const respuesta = await contenedor.renderToResponse(componente as never, { props });
  return { respuesta, html: await respuesta.text() };
}

describe('páginas de error', () => {
  it.each(PAGINAS)('la de $codigo responde con ese estado', async ({ codigo, componente }) => {
    const { respuesta } = await renderizar(componente);
    // Lo que se prueba es justamente lo que no sale gratis: una página
    // renderizada responde 200 salvo que fije su estado a mano.
    expect(respuesta.status).toBe(codigo);
  });

  it.each(PAGINAS)('la de $codigo se explica al visitante', async ({ codigo, componente, encabezado }) => {
    const { html } = await renderizar(componente);
    expect(html).toContain(`Error ${codigo}`);
    expect(html).toContain(encabezado);
  });

  it.each(PAGINAS)('la de $codigo va noindex', async ({ componente }) => {
    const { html } = await renderizar(componente);
    // Un error indexado es tráfico de búsqueda que aterriza en una vía muerta.
    expect(html).toContain('<meta name="robots" content="noindex, nofollow">');
  });

  it('el 500 no filtra el detalle del error', async () => {
    const { html } = await renderizar(Pagina500, {
      error: new Error('fallo al conectar con SUPABASE_SERVICE_KEY=secretazo'),
    });
    // Astro pasa la causa del fallo en `Astro.props.error`. Mostrarla revelaría
    // rutas, consultas o credenciales: su lugar son los logs del servidor.
    expect(html).not.toContain('secretazo');
    expect(html).not.toContain('SUPABASE_SERVICE_KEY');
  });
});

describe('acceso a las rutas de administración', () => {
  const usuario = { id: 'u1', email: 'ana@carflip.cl', app_metadata: {} };
  const admin = { id: 'u2', email: 'admin@carflip.cl', app_metadata: { rol: 'admin' } };

  let next: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sesion.usuario = null;
    next = vi.fn(
      async () => new Response('<html></html>', { headers: { 'content-type': 'text/html' } }),
    );
  });

  function contexto(ruta: string): APIContext {
    const url = new URL(`https://carflip.cl${ruta}`);
    return {
      url,
      request: new Request(url),
      locals: {},
      cookies: {},
      redirect: (destino: string, estado = 302) =>
        new Response(null, { status: estado, headers: { location: destino } }),
    } as unknown as APIContext;
  }

  it('manda a /entrar a quien no tiene sesión, no al 403', async () => {
    const respuesta = await onRequest(contexto('/dashboard'), next as never);

    expect(next).not.toHaveBeenCalled();
    expect(respuesta.status).toBe(302);
    expect(respuesta.headers.get('location')).toBe('/entrar?volver=%2Fdashboard');
  });

  it('responde 403 sobre la misma URL a la sesión sin rol', async () => {
    sesion.usuario = usuario;
    await onRequest(contexto('/dashboard'), next as never);

    // La reescritura conserva la URL: el visitante ve por qué no puede entrar
    // en vez de aparecer en el home sin explicación.
    expect(next).toHaveBeenCalledWith('/403');
  });

  it('deja pasar al administrador sin reescribir', async () => {
    sesion.usuario = admin;
    await onRequest(contexto('/dashboard'), next as never);

    expect(next).toHaveBeenCalledWith(undefined);
  });

  it('no toca las rutas públicas', async () => {
    const respuesta = await onRequest(contexto('/avisos'), next as never);

    expect(next).toHaveBeenCalledWith(undefined);
    expect(respuesta.status).toBe(200);
  });

  it('mantiene el redirect en /api/moderacion, que se invoca desde formularios', async () => {
    sesion.usuario = usuario;
    const respuesta = await onRequest(contexto('/api/moderacion/7'), next as never);

    expect(next).not.toHaveBeenCalled();
    expect(respuesta.status).toBe(302);
    expect(respuesta.headers.get('location')).toBe('/');
  });

  it('aplica las cabeceras de seguridad también a la respuesta del 403', async () => {
    sesion.usuario = usuario;
    const respuesta = await onRequest(contexto('/dashboard'), next as never);

    // Reescribir con `next('/403')` en vez de cortar antes es lo que mantiene la
    // respuesta dentro de la pasada que fija estas cabeceras.
    expect(respuesta.headers.get('content-security-policy')).toContain("default-src 'self'");
    expect(respuesta.headers.get('x-content-type-options')).toBe('nosniff');
    expect(respuesta.headers.get('x-frame-options')).toBe('DENY');
  });
});
