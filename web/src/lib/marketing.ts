// Clases compartidas por las páginas de lectura corrida (/como-funciona,
// /quienes-somos y las legales): mismo ritmo editorial. Se centralizan aquí
// para no redefinirlas en cada página y que un cambio de ritmo sea un solo edit.
//
//   seccionCls → separación entre secciones (80px, 120px en desktop)
//   rubroCls   → rótulo en versalitas que encabeza cada sección
//   parrafoCls → copy largo (19px): un paso sobre el texto de producto, porque
//                estas páginas son de lectura corrida y no de escaneo

export const seccionCls = 'mb-section lg:mb-editorial';
export const rubroCls = 'text-base  uppercase tracking-widest mb-block';
export const parrafoCls = 'text-lg leading-relaxed';
