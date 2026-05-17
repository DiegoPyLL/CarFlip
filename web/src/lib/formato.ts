export function formatearPrecio(precio: number | null, moneda: string = 'CLP'): string {
  if (precio === null) return '—';
  return new Intl.NumberFormat('es-CL', { style: 'currency', currency: moneda, maximumFractionDigits: 0 }).format(precio);
}

export function formatearKm(km: number | null): string {
  if (km === null) return '—';
  return new Intl.NumberFormat('es-CL').format(km) + ' km';
}

export function formatearFecha(fecha: Date | null): string {
  if (!fecha) return '—';
  return new Intl.DateTimeFormat('es-CL', { day: 'numeric', month: 'short', year: 'numeric' }).format(fecha);
}

export function signosDelta(delta: number | null): { texto: string; clases: string } | null {
  if (delta === null || delta === 0) return null;
  if (delta < 0) {
    return { texto: `▼ ${Math.abs(delta).toFixed(1)}%`, clases: 'bg-green-100 text-green-700' };
  }
  return { texto: `▲ ${delta.toFixed(1)}%`, clases: 'bg-red-100 text-red-700' };
}
