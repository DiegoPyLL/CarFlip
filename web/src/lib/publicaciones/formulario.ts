/**
 * Lectura y validación del formulario de aviso, compartida por crear y editar.
 *
 * El navegador ya valida con `required`/`min`/`max`/`pattern`, pero eso es
 * comodidad, no seguridad: aquí se vuelve a validar todo, porque un POST puede
 * llegar sin pasar por el formulario.
 */

import { normalizarPatente } from '@lib/patente';
import { normalizar } from '@lib/sanitizar';

import { ANIO_MINIMO, COMBUSTIBLES, REGIONES, TRACCIONES, TRANSMISIONES, anioMaximo, comunaEnRegion } from './opciones';

export interface CamposAviso {
  marca: string;
  modelo: string;
  version: string | null;
  anio: number;
  km: number;
  precio: number;
  patente: string;
  combustible: string | null;
  transmision: string | null;
  traccion: string | null;
  ubicacion: string;
  descripcion: string | null;
  visible_en_deals: boolean;
}

const KM_MAXIMO = 2_000_000;
const PRECIO_MAXIMO = 999_000_000;

function entero(valor: FormDataEntryValue | null): number | null {
  const texto = String(valor ?? '').replace(/[.\s]/g, '');
  if (!/^\d+$/.test(texto)) return null;
  const numero = Number(texto);
  return Number.isSafeInteger(numero) ? numero : null;
}

function deLista<T extends string>(valor: FormDataEntryValue | null, lista: readonly T[]): T | null {
  const texto = String(valor ?? '').trim();
  return (lista as readonly string[]).includes(texto) ? (texto as T) : null;
}

/** Devuelve las columnas listas para escribir, o `null` si algo no valida. */
export function camposDelFormulario(datos: FormData): CamposAviso | null {
  // Honeypot: invisible para personas, un bot que autocompleta todo lo llena.
  if (String(datos.get('web') ?? '').length > 0) return null;

  const marca = normalizar(datos.get('marca'), { max: 100 });
  const modelo = normalizar(datos.get('modelo'), { max: 100 });
  const version = normalizar(datos.get('version'), { max: 100 });
  const descripcion = normalizar(datos.get('descripcion'), { max: 2000, preservarSaltos: true });

  const anio = entero(datos.get('anio'));
  const km = entero(datos.get('km'));
  const precio = entero(datos.get('precio'));
  const patente = normalizarPatente(datos.get('patente'));
  const region = deLista(datos.get('region'), REGIONES);
  const comuna = String(datos.get('comuna') ?? '').trim();
  const combustible = deLista(datos.get('combustible'), COMBUSTIBLES);
  const transmision = deLista(datos.get('transmision'), TRANSMISIONES);
  const traccion = deLista(datos.get('traccion'), TRACCIONES);

  if (!marca || !modelo || !patente) return null;
  // El par tiene que ser coherente, no solo existir cada parte: "Arica,
  // Metropolitana" es una `ubicacion` imposible y rompería el filtro por región.
  if (!region || !comunaEnRegion(region, comuna)) return null;
  if (anio === null || anio < ANIO_MINIMO || anio > anioMaximo()) return null;
  if (km === null || km > KM_MAXIMO) return null;
  if (precio === null || precio <= 0 || precio > PRECIO_MAXIMO) return null;

  // `titulo` no está acá: lo deriva la base desde marca/modelo/versión/año
  // (trigger `particulares_deriva_campos`, migración 0018), que es lo que impide
  // que sea texto libre para quien escriba por PostgREST en vez de por el form.
  return {
    marca,
    modelo,
    version: version || null,
    anio,
    km,
    precio,
    patente,
    combustible,
    transmision,
    traccion,
    ubicacion: `${comuna}, ${region}`,
    descripcion: descripcion || null,
    // Un checkbox solo se envía cuando está marcado; su ausencia es el opt-out.
    visible_en_deals: datos.get('visible_en_deals') !== null,
  };
}
