/**
 * Vocabulario de `/cuenta/seguridad`: los códigos que los endpoints ponen en la
 * querystring y el texto que la página muestra por cada uno.
 *
 * Vive aparte porque cuatro endpoints y una página tienen que coincidir en las
 * mismas claves, y un código suelto en un `redirect` no lo comprueba nadie. Es
 * el mismo criterio de `MENSAJE_ERROR` en `publicaciones/limites.ts`, pero con
 * su propio catálogo: aquello habla de avisos y esto de credenciales.
 */

export const RUTA_SEGURIDAD = '/cuenta/seguridad';

export type ErrorSeguridad =
  | 'config'
  | 'correo_invalido'
  | 'correo_igual'
  | 'correo_en_uso'
  | 'correo_sin_cambio'
  | 'correo_codigo'
  | 'clave_corta'
  | 'clave_distinta'
  | 'clave_repetida'
  | 'clave_debil'
  | 'reautenticar'
  | 'nonce_invalido'
  | 'servidor';

export const MENSAJE_SEGURIDAD: Record<ErrorSeguridad, string> = {
  config: 'Esta sección no está disponible en este momento.',
  correo_invalido: 'Ingresa un correo electrónico válido.',
  correo_igual: 'Ese ya es tu correo actual.',
  correo_en_uso: 'No pudimos usar ese correo. Prueba con otro.',
  correo_sin_cambio: 'No hay ningún cambio de correo en curso.',
  // Con la confirmación doble activa, un código errado quema el par: hay que
  // pedir códigos nuevos, y el mensaje tiene que decirlo o el usuario reintenta
  // con los viejos hasta rendirse.
  correo_codigo: 'Alguno de los códigos no es válido o ya expiró. Pide códigos nuevos y vuelve a intentarlo.',
  clave_corta: 'La contraseña nueva debe tener al menos 8 caracteres.',
  clave_distinta: 'Las dos contraseñas no coinciden.',
  clave_repetida: 'La contraseña nueva tiene que ser distinta de la actual.',
  clave_debil: 'Esa contraseña es demasiado fácil de adivinar. Prueba con una más larga.',
  reautenticar: 'Por seguridad necesitamos confirmar que eres tú. Te enviamos un código a tu correo.',
  nonce_invalido: 'El código de confirmación no es válido o ya expiró. Pide uno nuevo.',
  servidor: 'No pudimos completar la operación. Inténtalo de nuevo.',
};

export type EstadoSeguridad =
  | 'recuperacion'
  | 'correo_enviado'
  | 'correo_guardado'
  | 'contrasena_guardada'
  | 'nonce_enviado';

export const AVISO_SEGURIDAD: Record<EstadoSeguridad, string> = {
  recuperacion: 'Verificamos tu identidad. Elige una contraseña nueva para terminar.',
  correo_enviado: 'Te enviamos un código a cada dirección: la actual y la nueva. Necesitamos los dos.',
  correo_guardado: 'Tu correo quedó actualizado.',
  contrasena_guardada: 'Tu contraseña quedó actualizada.',
  nonce_enviado: 'Te enviamos un código a tu correo. Escríbelo para confirmar el cambio.',
};

/** Traduce un código recibido por querystring, ignorando cualquier valor ajeno al catálogo. */
export function mensajeDeSeguridad(codigo: string | null): string | null {
  if (!codigo) return null;
  return codigo in MENSAJE_SEGURIDAD
    ? MENSAJE_SEGURIDAD[codigo as ErrorSeguridad]
    : MENSAJE_SEGURIDAD.servidor;
}

/** Igual que la anterior, pero para los avisos de éxito: un valor ajeno no muestra nada. */
export function avisoDeSeguridad(codigo: string | null): string | null {
  if (!codigo) return null;
  return codigo in AVISO_SEGURIDAD ? AVISO_SEGURIDAD[codigo as EstadoSeguridad] : null;
}
