/**
 * Patentes chilenas según el D.S. 17 del MTT y la Ley 18.290 de Tránsito.
 *
 * Cuatro formatos vigentes conviven en la calle; el largo total distingue el
 * tipo de vehículo (6 caracteres = auto, 5 = moto):
 *
 * - Autos desde 2007:      4 letras + 2 dígitos (GSBB20)
 * - Autos anteriores:      2 letras + 4 dígitos (AA1000)
 * - Motos desde 2007:      3 letras + 2 dígitos (BJH61)
 * - Motos anteriores:      2 letras + 3 dígitos (AA123)
 *
 * La serie de 2007 no usa vocales ni M, N, Ñ, Q (se excluyeron por
 * legibilidad); la serie anterior admite el alfabeto completo.
 */

const FORMATO = /^(?:[A-Z]{2}\d{3,4}|[BCDFGHJKLPRSTVWXYZ]{3,4}\d{2})$/;

/** Canoniza (mayúsculas, sin separadores) y devuelve la patente, o `null` si no es válida. */
export function normalizarPatente(valor: unknown): string | null {
  const texto = String(valor ?? '')
    .toUpperCase()
    .replace(/[\s.·-]/g, '');
  return FORMATO.test(texto) ? texto : null;
}

/**
 * Agrupa como en la placa física: los autos estampan pares (GS·BB·20,
 * AA·10·00) y las motos separan letras de dígitos (BJH·61, AA·123).
 */
export function formatearPatente(patente: string): string {
  if (patente.length === 6) return patente.match(/.{2}/g)!.join('·');
  return patente.replace(/(\d+)$/, '·$1');
}
