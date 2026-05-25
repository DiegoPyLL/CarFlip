import { createClient, type SupabaseClient } from '@supabase/supabase-js';

export const POR_PAGINA = 24;

let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (_client) return _client;
  const url = (import.meta.env.SUPABASE_URL as string | undefined) ?? process.env.SUPABASE_URL;
  const key = (import.meta.env.SUPABASE_SERVICE_KEY as string | undefined) ?? process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    throw new Error('SUPABASE_URL y SUPABASE_SERVICE_KEY no están configuradas en las variables de entorno de Vercel');
  }
  _client = createClient(url, key);
  return _client;
}
