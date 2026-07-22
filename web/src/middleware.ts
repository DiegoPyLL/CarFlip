import { defineMiddleware } from 'astro:middleware';
import { AUTH_CONFIGURADA, crearClienteUsuario, tieneCookieSesion, urlEntrar } from '@lib/auth/servidor';

// Rutas que exigen sesión, y las que además exigen rol de administrador.
const PRIVADAS = ['/cuenta'];
const SOLO_ADMIN = ['/dashboard', '/api/moderacion'];

function cuelgaDe(ruta: string, prefijos: string[]): boolean {
  return prefijos.some((p) => ruta === p || ruta.startsWith(`${p}/`));
}

export const onRequest = defineMiddleware(async (context, next) => {
  const ruta = context.url.pathname.replace(/\/+$/, '') || '/';
  const requiereSesion = cuelgaDe(ruta, PRIVADAS) || cuelgaDe(ruta, SOLO_ADMIN);

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

  if (cuelgaDe(ruta, SOLO_ADMIN) && context.locals.usuario?.rol !== 'admin') {
    return context.redirect('/', 302);
  }

  const respuesta = await next();

  // Astro emite las respuestas SSR como `text/html` a secas. La declaración de
  // codificación queda entonces solo en el <meta charset> del layout y, aunque
  // ahí llega dentro de los primeros 1024 bytes, la cabecera es la que manda:
  // sin el parámetro, los auditores la dan por ausente.
  const tipo = respuesta.headers.get('content-type');
  if (tipo?.startsWith('text/html') && !tipo.includes('charset')) {
    respuesta.headers.set('content-type', 'text/html; charset=utf-8');
  }

  return respuesta;
});
