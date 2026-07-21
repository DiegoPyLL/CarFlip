import { createServerClient, parseCookieHeader } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { APIContext } from 'astro';

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

// Supabase nombra sus cookies de sesión `sb-<ref>-auth-token`. Comprobarlo evita
// una llamada de red a `getUser()` en cada visita anónima, que es la mayoría del
// tráfico y todo el tráfico indexable.
export function tieneCookieSesion(request: Request): boolean {
  return (request.headers.get('Cookie') ?? '').includes('sb-');
}

// Solo se aceptan rutas internas como destino de redirección: debe empezar con
// `/` y no con `//` (que el navegador interpreta como host externo).
export function rutaInterna(valor: string | null | undefined, porDefecto = '/'): string {
  return valor && valor.startsWith('/') && !valor.startsWith('//') ? valor : porDefecto;
}

export function urlEntrar(volver: string, error?: string): string {
  const destino = new URL('/entrar', 'https://carflip.cl');
  destino.searchParams.set('volver', volver);
  if (error) destino.searchParams.set('error', error);
  return destino.pathname + destino.search;
}
