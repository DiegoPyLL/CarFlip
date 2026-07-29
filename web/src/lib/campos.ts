/**
 * Normalización de lo que se escribe en un campo, según su contexto.
 *
 * Funciones puras e isomorfas: las importa igual el frontmatter de un `.astro`
 * —donde validan lo que llega por la URL o por un POST— que el `<script>` de
 * `components/Normalizacion.astro`, donde dan formato en vivo. Es la única
 * definición de la forma de cada dato, así que el navegador y el servidor no
 * pueden discrepar sobre qué es un precio o un kilometraje válido.
 *
 * Las canónicas de patente y teléfono viven aparte —`normalizarPatente` en
 * `patente.ts`, `normalizarTelefonoCL` en `sanitizar.ts`— porque rechazan lo
 * incompleto; las de acá aceptan un valor a medio escribir, que es lo que hay
 * mientras se teclea.
 */

import { RE } from './regex';

/** Deja solo los dígitos y recorta a `max` de ellos. */
export function digitos(valor: string, max: number): string {
  return valor.replace(/\D/g, '').slice(0, max);
}

/** "1500000" → "1.500.000". Cadena vacía si no hay ningún dígito. */
export function miles(valor: string, max: number): string {
  const limpio = digitos(valor, max);
  return limpio ? Number(limpio).toLocaleString('es-CL') : '';
}

/** "1500000" → "$1.500.000". */
export function montoCLP(valor: string, max: number): string {
  const formateado = miles(valor, max);
  return formateado ? `$${formateado}` : '';
}

/**
 * Inverso de `miles`: "1.500.000" → 1500000, o `null` si no es un entero.
 *
 * Tolera los puntos y espacios que pone el formato chileno, para que una URL
 * compartida con `?precio_max=1.500.000` filtre por el monto y no por 1,5 —que
 * es lo que devolvía el `parseFloat` que había antes.
 */
export function aEntero(valor: string | null | undefined): number | null {
  const texto = String(valor ?? '').replace(/[.\s]/g, '');
  if (!RE.entero.test(texto)) return null;
  const numero = Number(texto);
  return Number.isSafeInteger(numero) ? numero : null;
}

/** Patente mientras se escribe: mayúsculas, sin separadores, hasta 6 caracteres. */
export function tecleoPatente(valor: string): string {
  return valor.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6);
}

/**
 * Móvil chileno mientras se escribe: "+56 9 1234 5678", agrupando de a poco.
 *
 * El prefijo es fijo, así que se descarta si ya viene tipeado o pegado: solo
 * los ocho dígitos del abonado son del usuario. Al primer dígito aparece
 * "+56 9" para que se vea que el resto ya está puesto.
 */
export function tecleoTelefonoCL(valor: string): string {
  let numero = valor.replace(/\D/g, '');
  if (!numero) return '';
  if (numero.startsWith('56')) numero = numero.slice(2);
  if (numero.startsWith('9')) numero = numero.slice(1);
  numero = numero.slice(0, 8);
  return ['+56 9', numero.slice(0, 4), numero.slice(4)].filter(Boolean).join(' ');
}

/** Texto libre al enviar: colapsa los espacios y recorta los extremos. */
export function textoLimpio(valor: string): string {
  return valor.replace(/\s+/g, ' ').trim();
}
