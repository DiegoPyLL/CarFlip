/**
 * Catálogo de expresiones regulares del sitio.
 *
 * Cada forma se escribe una sola vez, sin anclas, porque así es como la pide el
 * atributo `pattern` de un `<input>` —el navegador la ancla solo— y de ahí se
 * deriva la versión anclada que valida el servidor. Antes cada patrón estaba
 * transcrito a mano en los dos lados (el `pattern` de la patente prometía en un
 * comentario ser "espejo exacto" de `patente.ts`, y `NOMBRE_RE` vivía duplicada
 * en dos endpoints), que es justo lo que se rompe en silencio al editar uno.
 */

/** Fuente sin anclar: se interpola tal cual como atributo `pattern` de un `<input>`. */
export const PATRON = {
  /**
   * Las cuatro series de patente chilena vigentes (D.S. 17 del MTT). Acepta
   * minúsculas porque es lo que se tipea; el servidor pasa a mayúsculas antes
   * de validar.
   */
  patente: '[A-Za-z]{2}[0-9]{3,4}|[BbCcDdFfGgHhJjKkLlPpRrSsTtVvWwXxYyZz]{3,4}[0-9]{2}',
  /** Nombre de persona: letras de cualquier alfabeto y espacios, sin dígitos. */
  nombre: '[\\p{L}\\s]+',
  /** Forma mínima de un correo; quien decide si existe es el mensaje que se le envía. */
  email: '[^\\s@]+@[^\\s@]+\\.[^\\s@]+',
  /** Móvil chileno tal como lo escribe la gente: con o sin +56, con o sin espacios. */
  telefonoCL: '(\\+?56)?\\s?9\\s?\\d{4}\\s?\\d{4}',
  /** Código de verificación del registro. */
  codigo: '[0-9]{8}',
  /** Entero pelado, sin separadores. */
  entero: '[0-9]+',
  /** Lo que acepta un campo de monto mientras se tipea, ya con sus puntos de miles. */
  monto: '[0-9$.\\s]*',
} as const;

/** La misma fuente, anclada, para validar en el servidor. */
const anclada = (fuente: string) => new RegExp(`^(?:${fuente})$`, 'u');

export const RE = {
  patente: anclada(PATRON.patente),
  nombre: anclada(PATRON.nombre),
  email: anclada(PATRON.email),
  entero: anclada(PATRON.entero),
  /** Móvil ya limpio de separadores: no tiene par en ningún `pattern`. */
  movilCL: /^9\d{8}$/,
} as const;
