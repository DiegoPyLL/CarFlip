import type { APIRoute } from 'astro';
import { escaparHtml, normalizar } from '@lib/sanitizar';

export const prerender = false;

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

export const POST: APIRoute = async ({ request, url }) => {
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
