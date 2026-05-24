/**
 * Normalización de términos de búsqueda usando similitud por trigramas (Dice coefficient).
 * Permite encontrar "Peugeot" aunque el usuario escriba "peugot".
 */

function trigramas(s: string): Set<string> {
  const padded = `  ${s.toLowerCase()}  `;
  const set = new Set<string>();
  for (let i = 0; i <= padded.length - 3; i++) {
    set.add(padded.slice(i, i + 3));
  }
  return set;
}

function similitudDice(a: string, b: string): number {
  const sa = trigramas(a);
  const sb = trigramas(b);
  let comunes = 0;
  for (const g of sa) if (sb.has(g)) comunes++;
  return (2 * comunes) / (sa.size + sb.size);
}

/**
 * Si el término tiene suficiente similitud con alguna marca conocida (≥ 0.4),
 * devuelve la marca corregida. Si no, devuelve el término original.
 *
 * Ejemplos:
 *   "peugot"    → "Peugeot"    (similitud ≈ 0.71)
 *   "toyotta"   → "Toyota"     (similitud ≈ 0.72)
 *   "jeep"      → "Jeep"       (similitud = 1.0)
 *   "corolla"   → "corolla"    (no es marca, similitud baja con todas → sin cambio)
 */
export function normalizarBusqueda(termino: string, marcas: string[]): string {
  if (!termino || termino.length < 3) return termino;

  let mejorSim = 0;
  let mejorMarca = '';

  for (const marca of marcas) {
    const sim = similitudDice(termino, marca);
    if (sim > mejorSim) {
      mejorSim = sim;
      mejorMarca = marca;
    }
  }

  return mejorSim >= 0.4 ? mejorMarca : termino;
}
