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

export function formatearDuracion(segundos: number | null): string {
  if (segundos === null) return '—';
  const s = Math.round(segundos);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function formatearFechaHora(fecha: Date | null): string {
  if (!fecha) return '—';
  return new Intl.DateTimeFormat('es-CL', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(fecha);
}

export function signosDelta(delta: number | null): { texto: string; clases: string } | null {
  if (delta === null || delta === 0) return null;
  if (delta < 0) {
    return { texto: `▼ ${Math.abs(delta).toFixed(1)}%`, clases: 'bg-green-100 text-green-700' };
  }
  return { texto: `▲ ${delta.toFixed(1)}%`, clases: 'bg-red-100 text-red-700' };
}
