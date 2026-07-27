import { describe, expect, it, vi } from 'vitest';

// `avisos.ts` arrastra el cliente de servicio, que exige credenciales al
// importarse; acá solo se prueba cómo construye la consulta.
vi.mock('@lib/db/client', () => ({ supabase: {}, POR_PAGINA: 24 }));

const { aplicarFiltros } = await import('@lib/db/avisos');

/**
 * `?modelo=` es el único filtro que se interpola dentro de una expresión `or()`
 * de PostgREST, donde la coma, el punto y los paréntesis son gramática y no
 * texto. Sin escapar, un `zzz,anio.gte.1900` se parseaba como un término más:
 * el visitante filtraba por columnas que no eligió y rompía la consulta con un
 * 400 que subía como 500 a /avisos, /deals y /mercado.
 *
 * Se comprueba la expresión que se construye, con un doble del builder: es lo
 * que viaja a PostgREST y no hace falta base de datos para verlo.
 */

function builderFalso() {
  const llamadas: { metodo: string; args: unknown[] }[] = [];
  const query: Record<string, unknown> = {};
  for (const metodo of ['or', 'ilike', 'eq', 'gte', 'lte']) {
    query[metodo] = (...args: unknown[]) => {
      llamadas.push({ metodo, args });
      return query;
    };
  }
  return { query, llamadas };
}

const expresionOr = (modelo: string): string => {
  const { query, llamadas } = builderFalso();
  aplicarFiltros(query, { modelo });
  const or = llamadas.find((l) => l.metodo === 'or');
  return String(or?.args[0] ?? '');
};

/**
 * Separa la expresión como lo hace PostgREST: la coma delimita términos, pero no
 * dentro de un valor entre comillas, donde la barra invertida escapa al carácter
 * siguiente. Es la parte que importa: mientras el payload no consiga cerrar las
 * comillas, no puede abrir un término nuevo.
 */
function terminos(expr: string): string[] {
  const partes: string[] = [];
  let actual = '';
  let enComillas = false;

  for (let i = 0; i < expr.length; i++) {
    const c = expr[i];
    if (enComillas && c === '\\') {
      actual += c + (expr[i + 1] ?? '');
      i++;
    } else if (c === '"') {
      enComillas = !enComillas;
      actual += c;
    } else if (c === ',' && !enComillas) {
      partes.push(actual);
      actual = '';
    } else {
      actual += c;
    }
  }
  partes.push(actual);
  return partes;
}

/** Las columnas sobre las que la expresión termina filtrando de verdad. */
const columnasFiltradas = (expr: string): string[] => terminos(expr).map((t) => t.split('.')[0]);

describe('aplicarFiltros — término de búsqueda dentro de or()', () => {
  it('busca en título, marca y modelo con el valor entre comillas', () => {
    const expr = expresionOr('Corolla');
    expect(expr).toBe('titulo.ilike."%Corolla%",marca.ilike."%Corolla%",modelo.ilike."%Corolla%"');
  });

  it('no deja que una coma abra un término nuevo de la expresión', () => {
    // El payload del advisory: sin escapar, `anio.gte.1900%` se casteaba a
    // integer y PostgREST devolvía un 400 que subía como 500 al listado.
    expect(columnasFiltradas(expresionOr('zzz,anio.gte.1900'))).toEqual(['titulo', 'marca', 'modelo']);
  });

  it('no deja inyectar un filtro sobre otra columna ni cerrar el paréntesis', () => {
    for (const payload of [
      'zzz,id.gte.0',
      'zzz),or=(id.gte.0',
      'zzz,usuario_id.not.is.null',
      'zzz,estado.neq.publicado',
    ]) {
      expect(columnasFiltradas(expresionOr(payload))).toEqual(['titulo', 'marca', 'modelo']);
    }
  });

  it('escapa las comillas y las barras invertidas, que son lo único especial dentro del valor', () => {
    expect(expresionOr('a"b')).toContain('"%a\\"b%"');
    expect(expresionOr('a\\b')).toContain('"%a\\\\b%"');
    // Intentos de cerrar las comillas para salir del valor: con `"` escapada, la
    // coma que sigue queda dentro del término y no separa nada.
    expect(columnasFiltradas(expresionOr('a",anio.gte.1900,"b'))).toEqual(['titulo', 'marca', 'modelo']);
    expect(columnasFiltradas(expresionOr('a\\",anio.gte.1900'))).toEqual(['titulo', 'marca', 'modelo']);
  });

  it('deja intactos los términos legítimos con paréntesis, punto o acento', () => {
    expect(expresionOr('Golf (mk7)')).toContain('"%Golf (mk7)%"');
    expect(expresionOr('Serie 3.0')).toContain('"%Serie 3.0%"');
    expect(expresionOr('Citroën')).toContain('"%Citroën%"');
  });
});
