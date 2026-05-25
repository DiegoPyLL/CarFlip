import { getSupabase } from './client';
import type { Aviso } from '../tipos';

type RawAviso = {
  id: number;
  id_externo: string;
  url: string;
  titulo: string;
  precio: string | null;
  moneda: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  km: number | null;
  ubicacion: string | null;
  combustible: string | null;
  descripcion: string | null;
  url_imagen: string | null;
  disponible: boolean | null;
  precio_anterior: string | null;
  delta_pct: number | null;
  primera_vez_visto: string | null;
  ultima_vez_visto: string | null;
};

function mapearAviso(row: RawAviso, fuente: 'autocosmos' | 'yapo'): Aviso {
  return {
    ...row,
    fuente,
    precio: row.precio !== null ? parseFloat(row.precio) : null,
    precio_anterior: row.precio_anterior !== null ? parseFloat(row.precio_anterior) : null,
    primera_vez_visto: row.primera_vez_visto ? new Date(row.primera_vez_visto) : null,
    ultima_vez_visto: row.ultima_vez_visto ? new Date(row.ultima_vez_visto) : null,
  } as unknown as Aviso;
}

export async function obtenerDeals(fuente?: 'autocosmos' | 'yapo', limite = 48): Promise<Aviso[]> {
  const THRESHOLD = -5;

  async function queryTabla(tabla: string, src: 'autocosmos' | 'yapo') {
    const { data } = await getSupabase()
      .from(tabla)
      .select('*')
      .lt('delta_pct', THRESHOLD)
      .not('precio', 'is', null)
      .not('delta_pct', 'is', null)
      .eq('disponible', true)
      .order('delta_pct', { ascending: true })
      .limit(limite);
    return (data ?? []).map(r => mapearAviso(r as RawAviso, src));
  }

  if (fuente === 'autocosmos') return queryTabla('autocosmos_listings', 'autocosmos');
  if (fuente === 'yapo')       return queryTabla('yapo_listings', 'yapo');

  const [ac, yp] = await Promise.all([
    queryTabla('autocosmos_listings', 'autocosmos'),
    queryTabla('yapo_listings', 'yapo'),
  ]);

  return [...ac, ...yp]
    .sort((a, b) => (a.delta_pct ?? 0) - (b.delta_pct ?? 0))
    .slice(0, limite);
}
