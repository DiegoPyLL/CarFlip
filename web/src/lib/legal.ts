// Constantes compartidas por los tres documentos legales (/condiciones-de-uso,
// /privacidad y /legal). Viven fuera de `Legal.astro` porque un componente Astro
// no exporta valores importables, y fuera de `@lib/marketing` porque el
// `rubroCls` de ahí es el rótulo en versalitas de las páginas de marketing:
// mismo nombre, otro rol.

/** Los tres documentos se revisan juntos: una sola fecha para los tres. */
export const ACTUALIZADO = '29 de julio de 2026';

/**
 * Identificación de quien responde por el sitio. La consumen `Responsable.astro`
 * —el bloque visible de /legal y /privacidad— y el JSON-LD de la portada, que
 * declara a la misma persona como `publisher`. Comparten origen a propósito: un
 * marcado que no coincide con el contenido visible es exactamente lo que las
 * guías de datos estructurados tratan como engañoso.
 *
 * CarFlip es un proyecto personal, sin sociedad detrás, así que la entidad es
 * una persona y no una organización.
 */
export const RESPONSABLE = {
  nombre: 'Diego Peña y Lillo',
  calidad: 'persona natural',
  domicilio: 'Huechuraba, Región Metropolitana, Chile',
  correo: 'dpenaylilloluhrs@gmail.com',
  perfil: 'https://github.com/DiegoPyLL',
};

/** Encabezado de sección dentro de un documento legal. */
export const rubroCls = 'text-2xl text-ink mb-element';

/** Enlace dentro del cuerpo de un documento legal. */
export const enlaceCls = 'text-ink underline underline-offset-4';

/**
 * Nombre canónico de cada documento. `Legal.astro` arma el pie "Ver también"
 * quitando la página actual, y la columna Legal del footer usa esta misma
 * lista: así los tres nombres no pueden desalinearse entre sí.
 */
export const DOCUMENTOS = [
  { href: '/condiciones-de-uso', texto: 'Condiciones de Uso' },
  { href: '/privacidad',         texto: 'Política de Privacidad' },
  { href: '/legal',              texto: 'Aviso Legal' },
];
