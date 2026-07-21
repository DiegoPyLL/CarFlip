import { defineMiddleware } from 'astro:middleware';
import { AUTH_CONFIGURADA, crearClienteUsuario, tieneCookieSesion, urlEntrar } from '@lib/auth/servidor';

// Rutas que exigen sesión, y las que además exigen rol de administrador.
const PRIVADAS = ['/cuenta'];
const SOLO_ADMIN = ['/dashboard'];

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

  return next();
});
