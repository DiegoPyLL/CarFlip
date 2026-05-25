import { createClient } from '@supabase/supabase-js';

const supabaseUrl = (import.meta.env.SUPABASE_URL as string) || (process.env.SUPABASE_URL as string);
const supabaseKey = (import.meta.env.SUPABASE_SERVICE_KEY as string) || (process.env.SUPABASE_SERVICE_KEY as string);

if (!supabaseUrl || !supabaseKey) {
  throw new Error('SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar definidas en web/.env');
}

export const supabase = createClient(supabaseUrl, supabaseKey);
export const POR_PAGINA = 24;
