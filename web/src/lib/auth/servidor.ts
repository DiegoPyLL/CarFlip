import { createServerClient, parseCookieHeader } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { APIContext, AstroCookies } from 'astro';

// Cliente con la anon key, sujeto a las políticas RLS y ligado a la sesión que
// viaja en las cookies de la request. Convive con el de `db/client.ts`, que usa
// la service key y bypassa RLS para las lecturas públicas de los scrapers.
const supabaseUrl =
  (import.meta.env.PUBLIC_SUPABASE_URL as string) || (process.env.PUBLIC_SUPABASE_URL as string);
const supabaseAnonKey =
  (import.meta.env.PUBLIC_SUPABASE_ANON_KEY as string) || (process.env.PUBLIC_SUPABASE_ANON_KEY as string);

// Sin las variables el sitio público debe seguir en pie: el módulo no lanza al
// importarse (el middleware lo importa en cada request). Solo la autenticación
// queda deshabilitada, y las rutas de /api/auth lo informan explícitamente.
export const AUTH_CONFIGURADA = Boolean(supabaseUrl && supabaseAnonKey);

export type ContextoAuth = Pick<APIContext, 'request' | 'cookies'>;

export function crearClienteUsuario({ request, cookies }: ContextoAuth): SupabaseClient {
  return createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll: () =>
        parseCookieHeader(request.headers.get('Cookie') ?? '').map(({ name, value }) => ({
          name,
          value: value ?? '',
        })),
      // `httpOnly` no es negociable: la cookie de sesión no debe ser legible
      // desde JavaScript. Los demás atributos se fijan aquí en vez de confiar
      // en los defaults de la librería.
      setAll: (nuevas) => {
        for (const { name, value, options } of nuevas) {
          cookies.set(name, value, {
            path: options?.path ?? '/',
            maxAge: options?.maxAge,
            expires: options?.expires,
            domain: options?.domain,
            httpOnly: true,
            sameSite: 'lax',
            secure: import.meta.env.PROD,
          });
        }
      },
    },
  });
}

// Supabase nombra su cookie de sesión `sb-<ref>-auth-token`, y la parte en
// `...auth-token.0`/`.1` cuando el token no cabe en una sola. El `<ref>` es el
// subdominio del proyecto.
// Sin las variables de entorno el módulo no debe lanzar al importarse (lo hace el
// middleware en cada request); ahí `AUTH_CONFIGURADA` es false y esto no se usa.
export const COOKIE_SESION = `sb-${(supabaseUrl ?? '').replace(/^https?:\/\//, '').split('.')[0]}-auth-token`;

/**
 * Si la request trae la cookie de sesión de este proyecto.
 *
 * Comprobarlo evita una llamada de red a `getUser()` en cada visita anónima, que
 * es la mayoría del tráfico y todo el tráfico indexable. Se exige el nombre
 * exacto: con un `includes('sb-')` cualquiera podía mandar `Cookie: sb-x=1` y
 * forzar la validación contra Supabase en cada petición, anulando el ahorro a
 * voluntad. Fijar *esta* cookie con basura sigue costando una llamada, pero eso
 * ya no se consigue con una cookie cualquiera.
 */
export function tieneCookieSesion(request: Request): boolean {
  return parseCookieHeader(request.headers.get('Cookie') ?? '').some(
    ({ name, value }) =>
      Boolean(value) && (name === COOKIE_SESION || name.startsWith(`${COOKIE_SESION}.`)),
  );
}

/**
 * Correo a la espera de confirmarse, entre el POST de /registro y el formulario
 * del código.
 *
 * Hace falta porque el registro responde con un redirect (patrón POST-Redirect-Get)
 * y el GET que sigue ya no ve el formulario. No es una credencial —la credencial
 * es el código que llega por correo— así que solo ahorra teclearlo de nuevo: el
 * campo queda editable para quien confirme desde otro dispositivo, donde esta
 * cookie no existe. Va `httpOnly` igual, para no dejar el correo a la vista de
 * cualquier script de la página.
 */
export const COOKIE_EMAIL_PENDIENTE = 'cf-email-pendiente';

// Algo más que la vigencia del código, para que la cookie no caduque antes que él.
const VIGENCIA_EMAIL_PENDIENTE = 60 * 30;

export function guardarEmailPendiente(cookies: AstroCookies, email: string): void {
  cookies.set(COOKIE_EMAIL_PENDIENTE, email, {
    path: '/',
    maxAge: VIGENCIA_EMAIL_PENDIENTE,
    httpOnly: true,
    sameSite: 'lax',
    secure: import.meta.env.PROD,
  });
}

export function olvidarEmailPendiente(cookies: AstroCookies): void {
  cookies.delete(COOKIE_EMAIL_PENDIENTE, { path: '/' });
}

const ORIGEN = 'https://carflip.cl';

/**
 * Destino de redirección restringido a rutas de este sitio.
 *
 * No basta con exigir `/` y descartar `//`: la barra invertida también abre un
 * host externo, porque el parser de URL de WHATWG —navegadores y Node— normaliza
 * `\` a `/`, así que `/\evil.com` resuelve a `https://evil.com`. Por eso se
 * resuelve la URL de verdad y se compara el origen, en vez de mirar los primeros
 * caracteres: cubre la barra invertida, el esquema absoluto y los caracteres de
 * control de una sola vez. Lo que vuelve es la ruta ya normalizada.
 */
export function rutaInterna(valor: string | null | undefined, porDefecto = '/'): string {
  if (!valor || !valor.startsWith('/')) return porDefecto;
  try {
    const destino = new URL(valor, ORIGEN);
    if (destino.origin !== ORIGEN) return porDefecto;
    return destino.pathname + destino.search + destino.hash;
  } catch {
    return porDefecto;
  }
}

export function urlEntrar(volver: string, error?: string): string {
  const destino = new URL('/entrar', ORIGEN);
  destino.searchParams.set('volver', volver);
  if (error) destino.searchParams.set('error', error);
  return destino.pathname + destino.search;
}
