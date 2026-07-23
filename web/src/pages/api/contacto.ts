import type { APIRoute } from 'astro';
import { escaparHtml, normalizar } from '@lib/sanitizar';

export const prerender = false;

// Rate limit por IP: el honeypot no frena un script dirigido, y cada envío
// válido gasta cuota de Resend. Se permiten pocas solicitudes por ventana corta.
const RATE_LIMITE = 5;
const RATE_VENTANA_MIN = 10;
// Salt del hash de IP: no se guarda la IP en claro (minimización de datos,
// Ley 21.719). Se puede sobreescribir por entorno.
const RATE_SALT = (import.meta.env.CONTACT_RATE_SALT as string) || 'carflip-contacto';

async function hashIp(ip: string): Promise<string> {
  const datos = new TextEncoder().encode(`${RATE_SALT}:${ip}`);
  const buffer = await crypto.subtle.digest('SHA-256', datos);
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Registra el intento y responde si la IP superó el tope en la ventana. El
 * cliente de servicio se importa aquí (no al tope) para no acoplar el formulario
 * a la config de la base, y falla abierto: cualquier problema del registro no
 * bloquea el contacto, solo se pierde esta capa (Vercel Firewall es la otra).
 */
async function superaRateLimit(ip: string): Promise<boolean> {
  try {
    const { supabase: servicio } = await import('@lib/db/client');
    const ipHash = await hashIp(ip);
    const desde = new Date(Date.now() - RATE_VENTANA_MIN * 60 * 1000).toISOString();

    const { count } = await servicio
      .from('contacto_solicitudes')
      .select('id', { count: 'exact', head: true })
      .eq('ip_hash', ipHash)
      .gte('creado_en', desde);

    await servicio.from('contacto_solicitudes').insert({ ip_hash: ipHash });
    return (count ?? 0) >= RATE_LIMITE;
  } catch (error) {
    console.error('Rate limit de contacto no disponible:', error);
    return false;
  }
}

const RESEND_API_KEY = (import.meta.env.RESEND_API_KEY as string) || (process.env.RESEND_API_KEY as string);
const CONTACT_EMAIL =
  (import.meta.env.CONTACT_EMAIL as string) || (process.env.CONTACT_EMAIL as string) || 'dpenaylilloluhrs@gmail.com';
// Remitente de pruebas de Resend: válido sin verificar un dominio propio.
// Cambiar a algo como "CarFlip <contacto@carflip.cl>" cuando carflip.cl esté verificado en Resend.
const REMITENTE = 'CarFlip <onboarding@resend.dev>';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// El nombre solo admite letras (de cualquier idioma) y espacios: sin números ni signos.
const NOMBRE_RE = /^[\p{L}\s]+$/u;

function redirigir(origin: string, parametro: 'enviado' | 'error'): Response {
  const destino = new URL('/contacto', origin);
  destino.searchParams.set(parametro, '1');
  return Response.redirect(destino, 303);
}

export const POST: APIRoute = async ({ request, url, clientAddress }) => {
  const datos = await request.formData();

  // Honeypot: campo oculto para personas por CSS; un bot que completa todos
  // los campos del form lo llena y la respuesta se descarta en silencio.
  if (String(datos.get('web') ?? '').length > 0) {
    return redirigir(url.origin, 'enviado');
  }

  const nombre = normalizar(datos.get('nombre'), { max: 100 });
  const email = normalizar(datos.get('email'), { max: 200 }).toLowerCase();
  const mensaje = normalizar(datos.get('mensaje'), { max: 2000, preservarSaltos: true });

  if (!nombre || !email || !mensaje || !EMAIL_RE.test(email) || !NOMBRE_RE.test(nombre)) {
    return redirigir(url.origin, 'error');
  }

  if (!RESEND_API_KEY) {
    console.error('RESEND_API_KEY no está configurada');
    return redirigir(url.origin, 'error');
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
    return redirigir(url.origin, 'error');
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
    return redirigir(url.origin, 'error');
  }

  return redirigir(url.origin, 'enviado');
};
