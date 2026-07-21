// Clases compartidas por las páginas de marketing del sitio (/como-funciona y
// /quienes-somos): mismo ritmo editorial. Se centralizan aquí para no
// redefinirlas en cada página y que un cambio de ritmo sea un solo edit.
//
//   seccionCls       → separación entre secciones (80px, 120px en desktop)
//   rubroCls         → rótulo en versalitas que encabeza cada sección
//   gridEditorialCls → rubro descolgado a la izquierda desde lg, cuerpo en 64ch

export const seccionCls = 'mb-section lg:mb-editorial';
export const rubroCls = 'text-base  uppercase tracking-widest mb-block';
export const gridEditorialCls = 'grid gap-x-block lg:grid-cols-[9rem_minmax(0,64ch)]';
