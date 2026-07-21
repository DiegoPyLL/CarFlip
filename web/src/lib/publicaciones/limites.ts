/**
 * Topes anti-abuso de las publicaciones de particulares.
 *
 * La publicación es inmediata, sin cola de revisión, así que estos límites son
 * la única barrera previa al spam: el resto de la defensa es reactiva
 * (reportes + despublicación). Son funciones puras para poder testearlas sin
 * base de datos; quien las llama trae los conteos.
 *
 * Devuelven un **código**, no un mensaje: el código viaja en la querystring y la
 * página lo traduce contra este catálogo. Así nadie puede inyectar por URL un
 * texto arbitrario que la página mostraría como propio.
 */

export const LIMITES = {
  avisosActivos: 5,
  creacionesPor24h: 3,
  fotosPorAviso: 10,
  bytesPorFoto: 2 * 1024 * 1024,
  revelacionesPorDia: 20,
  /** Días sin actualizar tras los cuales un aviso pasa a `pausado`. */
  diasHastaExpirar: 60,
} as const;

export const TIPOS_FOTO = ['image/webp', 'image/jpeg', 'image/png'] as const;

export type MotivoError =
  | 'tope_activos'
  | 'tope_diario'
  | 'tope_fotos'
  | 'foto_pesada'
  | 'formato_foto'
  | 'tope_revelaciones'
  | 'email_sin_confirmar'
  | 'perfil_incompleto'
  | 'confirmacion'
  | 'datos'
  | 'no_encontrado'
  | 'servidor';

/** Lo que hay que escribir para confirmar el borrado de la cuenta. */
export const PALABRA_ELIMINAR = 'ELIMINAR';

export const MENSAJE_ERROR: Record<MotivoError, string> = {
  tope_activos: `Tienes ${LIMITES.avisosActivos} avisos publicados, el máximo permitido. Pausa o elimina uno para publicar otro.`,
  tope_diario: `Puedes publicar hasta ${LIMITES.creacionesPor24h} avisos por día. Inténtalo mañana.`,
  tope_fotos: `Cada aviso admite hasta ${LIMITES.fotosPorAviso} fotos.`,
  foto_pesada: 'Cada foto debe pesar menos de 2 MB.',
  formato_foto: 'Formato no admitido: usa JPG, PNG o WebP.',
  tope_revelaciones: `Alcanzaste el máximo de ${LIMITES.revelacionesPorDia} contactos por día.`,
  email_sin_confirmar: 'Confirma tu correo antes de publicar. Revisa el mensaje que te enviamos.',
  perfil_incompleto: 'Completa tu nombre y teléfono en tu cuenta antes de publicar.',
  confirmacion: `Escribe ${PALABRA_ELIMINAR} para confirmar que quieres borrar tu cuenta.`,
  datos: 'Revisa los datos del formulario e inténtalo de nuevo.',
  no_encontrado: 'No encontramos esa publicación.',
  servidor: 'No pudimos completar la operación. Inténtalo de nuevo.',
};

/** Traduce un código recibido por querystring, ignorando cualquier valor ajeno al catálogo. */
export function mensajeDeError(codigo: string | null): string | null {
  if (!codigo) return null;
  return codigo in MENSAJE_ERROR ? MENSAJE_ERROR[codigo as MotivoError] : MENSAJE_ERROR.servidor;
}

/** Devuelve el motivo del rechazo, o `null` si la acción está permitida. */
export function puedeCrearAviso(activos: number, creadosUltimas24h: number): MotivoError | null {
  if (activos >= LIMITES.avisosActivos) return 'tope_activos';
  if (creadosUltimas24h >= LIMITES.creacionesPor24h) return 'tope_diario';
  return null;
}

export function puedeSubirFoto(fotosActuales: number, bytes: number, tipo: string): MotivoError | null {
  if (fotosActuales >= LIMITES.fotosPorAviso) return 'tope_fotos';
  if (bytes > LIMITES.bytesPorFoto) return 'foto_pesada';
  if (!TIPOS_FOTO.includes(tipo as (typeof TIPOS_FOTO)[number])) return 'formato_foto';
  return null;
}

export function puedeRevelarContacto(revelacionesHoy: number): MotivoError | null {
  return revelacionesHoy >= LIMITES.revelacionesPorDia ? 'tope_revelaciones' : null;
}

/**
 * El borrado de cuenta exige escribir la palabra exacta. Es la única barrera —no
 * hay diálogo de confirmación, que exigiría JavaScript— así que no se admiten
 * variantes de mayúsculas: un "eliminar" suelto no debe borrar una cuenta.
 */
export function confirmacionValida(valor: string | null | undefined): boolean {
  return valor?.trim() === PALABRA_ELIMINAR;
}

/** Un perfil sin nombre ni teléfono válidos no puede publicar. */
export function perfilCompleto(perfil: { nombre: string | null; telefono: string | null } | null): boolean {
  return Boolean(perfil?.nombre?.trim() && perfil?.telefono?.trim());
}
