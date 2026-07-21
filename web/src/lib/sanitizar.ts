/** Saneamiento de texto entrado por usuarios, compartido por /contacto y las publicaciones. */

/**
 * Normaliza un campo antes de validarlo: unifica la forma Unicode (NFC),
 * elimina caracteres de control invisibles y colapsa espacios. `preservarSaltos`
 * conserva los saltos de línea; el resto queda en una sola línea.
 */
export function normalizar(
  valor: FormDataEntryValue | null,
  opciones: { max: number; preservarSaltos?: boolean },
): string {
  let texto = String(valor ?? '').normalize('NFC');
  // Elimina caracteres de control salvo tabulador (\t) y salto de línea (\n).
  texto = texto.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
  texto = opciones.preservarSaltos
    ? texto
        .replace(/\r\n?/g, '\n')
        .replace(/[^\S\n]+/g, ' ')
        .replace(/ *\n */g, '\n')
        .replace(/\n{3,}/g, '\n\n')
    : texto.replace(/\s+/g, ' ');
  return texto.trim().slice(0, opciones.max);
}

export function escaparHtml(texto: string): string {
  return texto
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Lleva un móvil chileno a la forma canónica `+56 9 XXXXXXXX`, o devuelve
 * `null` si no lo es. Se guarda normalizado para que el enlace de WhatsApp y el
 * `tel:` se armen sin volver a limpiar el dato en cada página.
 */
export function normalizarTelefonoCL(valor: FormDataEntryValue | null): string | null {
  const digitos = String(valor ?? '').replace(/\D/g, '');
  // Acepta 56912345678 y 912345678; ambos terminan en los mismos 8 dígitos.
  const nacional = digitos.startsWith('569') ? digitos.slice(2) : digitos;
  if (!/^9\d{8}$/.test(nacional)) return null;
  return `+56 9 ${nacional.slice(1)}`;
}
