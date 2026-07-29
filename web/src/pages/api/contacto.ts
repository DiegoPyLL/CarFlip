import type { APIRoute } from 'astro';
import { RE } from '@lib/regex';
import { escaparHtml, normalizar } from '@lib/sanitizar';

export const prerender = false;

// Rate limit por IP: el honeypot no frena un script dirigido, y cada envío
// válido gasta cuota de Resend. Se permiten pocas solicitudes por ventana corta.
const RATE_LIMITE = 5;
const RATE_VENTANA = '10 minutes';

/**
 * Salt del hash de IP: no se guarda la IP en claro (minimización de datos,
 * Ley 21.719). Sin un salt secreto el hash no protege nada —el espacio IPv4
 * entero se recorre por fuerza bruta en minutos si la tabla se filtra— así que no
 * cae en una constante del fuente, que en un repo público es de dominio público.
 * A falta de `CONTACT_RATE_SALT` se usa la service key: es server-only, estable
 * entre instancias y despliegues, y ya es requisito de este endpoint.
 */
const RATE_SALT =
  (import.meta.env.CONTACT_RATE_SALT as string) ||
  (process.env.CONTACT_RATE_SALT as string) ||
  (import.meta.env.SUPABASE_SERVICE_KEY as string) ||
  (process.env.SUPABASE_SERVICE_KEY as string);

async function hashIp(ip: string): Promise<string> {
  const datos = new TextEncoder().encode(`${RATE_SALT}:${ip}`);
  const buffer = await crypto.subtle.digest('SHA-256', datos);
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Si la IP superó el tope en la ventana. Registra el intento solo cuando está
 * dentro del tope: contarlos todos dejaba que un anónimo hiciera crecer la tabla
 * sin límite.
 *
 * La decisión y la escritura ocurren dentro de `registrar_solicitud_contacto`
 * (migración 0019), serializadas por IP: contar acá y después insertar era una
 * carrera por la que se colaban más solicitudes que el tope. El cliente de
 * servicio se importa aquí (no al tope) para no acoplar el formulario a la config
 * de la base, y falla abierto: un problema de la base no bloquea el contacto,
 * solo se pierde esta capa (Vercel Firewall es la otra).
 */
async function superaRateLimit(ip: string): Promise<boolean> {
  try {
    const { supabase: servicio } = await import('@lib/db/client');
    const { data, error } = await servicio.rpc('registrar_solicitud_contacto', {
      p_ip_hash: await hashIp(ip),
      p_ventana: RATE_VENTANA,
      p_tope: RATE_LIMITE,
    });
    if (error) throw error;
    return data === true;
  } catch (error) {
    console.error('Rate limit de contacto no disponible:', error);
    return false;
  }
}

const RESEND_API_KEY = (import.meta.env.RESEND_API_KEY as string) || (process.env.RESEND_API_KEY as string);
// Sin fallback: un correo de destino hardcodeado en un repo público es una
// dirección personal expuesta, y si la variable falta hay que enterarse.
const CONTACT_EMAIL = (import.meta.env.CONTACT_EMAIL as string) || (process.env.CONTACT_EMAIL as string);
// Remitente de pruebas de Resend: válido sin verificar un dominio propio.
// Cambiar a algo como "CarFlip <contacto@carflip.cl>" cuando carflip.cl esté verificado en Resend.
const REMITENTE = 'CarFlip <onboarding@resend.dev>';

export const POST: APIRoute = async ({ request, redirect, clientAddress }) => {
  // El `redirect` del contexto —el mismo que usa el resto de los endpoints— y no
  // `Response.redirect()`: esa respuesta nace con las cabeceras inmutables, y el
  // middleware, que le escribe las de seguridad, moría con un 500 (issue #45).
  const redirigir = (parametro: 'enviado' | 'error') => redirect(`/contacto?${parametro}=1`, 303);

  const datos = await request.formData();

  // Honeypot: campo oculto para personas por CSS; un bot que completa todos
  // los campos del form lo llena y la respuesta se descarta en silencio.
  if (String(datos.get('web') ?? '').length > 0) {
    return redirigir('enviado');
  }

  const nombre = normalizar(datos.get('nombre'), { max: 100 });
  const email = normalizar(datos.get('email'), { max: 200 }).toLowerCase();
  const mensaje = normalizar(datos.get('mensaje'), { max: 2000, preservarSaltos: true });

  if (!nombre || !email || !mensaje || !RE.email.test(email) || !RE.nombre.test(nombre)) {
    return redirigir('error');
  }

  if (!RESEND_API_KEY || !CONTACT_EMAIL || !RATE_SALT) {
    console.error('Falta RESEND_API_KEY, CONTACT_EMAIL o el salt del rate limit');
    return redirigir('error');
  }

  // `clientAddress` puede lanzar si el adapter no lo expone; sin IP no se aplica
  // el tope (se apoya en la capa de Vercel Firewall) pero el envío sigue.
  let ip = '';
  try {
    ip = clientAddress ?? '';
  } catch {
    /* sin IP */
  }
  if (ip && (await superaRateLimit(ip))) {
    return redirigir('error');
  }

  const respuesta = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: REMITENTE,
      to: CONTACT_EMAIL,
      reply_to: email,
      subject: `Contacto CarFlip — ${nombre}`,
      html: `<p><strong>Nombre:</strong> ${escaparHtml(nombre)}</p><p><strong>Email:</strong> ${escaparHtml(email)}</p><p><strong>Mensaje:</strong></p><p>${escaparHtml(mensaje).replace(/\r\n|\n/g, '<br>')}</p>`,
    }),
  });

  if (!respuesta.ok) {
    console.error('Error enviando correo de contacto:', await respuesta.text());
    return redirigir('error');
  }

  return redirigir('enviado');
};
