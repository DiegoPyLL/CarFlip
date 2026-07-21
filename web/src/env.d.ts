/// <reference types="astro/client" />
interface ImportMetaEnv {
  readonly SUPABASE_URL: string;
  readonly SUPABASE_SERVICE_KEY: string;
  readonly CDN_BASE_URL?: string;
  readonly PUBLIC_SUPABASE_URL: string;
  readonly PUBLIC_SUPABASE_ANON_KEY: string;
}

declare namespace App {
  interface Locals {
    // `null` solo si faltan las variables públicas de Supabase: el sitio
    // público sigue funcionando y la autenticación queda deshabilitada.
    supabase: import('@supabase/supabase-js').SupabaseClient | null;
    usuario: {
      id: string;
      email: string;
      emailConfirmado: boolean;
      rol: 'admin' | 'usuario';
    } | null;
  }
}
