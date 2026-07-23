# Seguridad — tareas de operación

Pasos que no viven en el código y hay que hacer en las consolas de Vercel /
Cloudflare / AWS. Complementan las medidas ya implementadas en el repo.

## Rate limit del contacto — capa de plataforma

El código ya limita `POST /api/contacto` por IP (tabla `contacto_solicitudes`,
migración 0012). Como segunda capa, añadir en **Vercel → Firewall** una regla de
_rate limit_ sobre la ruta `/api/contacto` (método POST) por IP. Corta el abuso
volumétrico antes de que llegue a la función y protege también la cuota de
invocaciones, no solo la de Resend.

## Variables de entorno — radio de impacto

El `.env` de la raíz mezcla secretos del scraper Python y de la web. Nunca ha
estado en el historial de git y `envDir:'../'` de Astro no filtra al cliente
(Vite solo expone `PUBLIC_*`), pero conviene acotar el radio de impacto:

- [ ] Rotar y acotar (least privilege) las claves IAM de larga vida
      `AWS_ACCESS_KEY_ID` / `S3_*`; idealmente migrar a R2-only o AWS Secrets
      Manager y retirarlas del `.env`.
- [ ] En el entorno del deploy **web** (Vercel) mantener solo lo que la web usa:
      `PUBLIC_SUPABASE_URL`, `PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_URL`,
      `SUPABASE_SERVICE_KEY`, `RESEND_API_KEY`, `CONTACT_EMAIL` y (opcional)
      `CONTACT_RATE_SALT`. Los secretos exclusivos del scraper (DB directa, R2,
      Groq, AWS/S3) no tienen por qué estar ahí.
- [ ] Definir `CONTACT_RATE_SALT` con un valor propio por entorno (el hash de IP
      del rate limit cae a un default si falta).

## Reporte de vulnerabilidades

Usar **GitHub Security Advisories** (borrador privado), no issues públicos: el
repositorio es público. Es la convención que ya sigue
`.github/workflows/auditoria.yml`.
