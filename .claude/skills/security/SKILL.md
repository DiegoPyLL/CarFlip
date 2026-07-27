---
name: security-audit
description: Auditoría de seguridad de CarFlip (web Astro/Vercel/Supabase y scraper Python) contra un checklist fijo de categorías. Se invoca únicamente a pedido explícito del usuario ("/security-audit", "audita la seguridad", "revisa seguridad del sitio") — no se dispara sola durante tareas normales de desarrollo.
---

# Auditoría de seguridad — CarFlip

Checklist propio, inspirado en el enfoque de NVIDIA SkillSpector (análisis estático por categorías, con severidad y evidencia concreta), pero adaptado a una web app real en vez de a paquetes de skills de IA. Es solo lectura: reporta, no modifica código salvo que el usuario pida arreglar algo puntual después de ver el reporte.

## Cómo ejecutar la auditoría

1. Recorre cada categoría de abajo revisando el código **actual** (no asumas que estas notas siguen vigentes; los archivos citados son puntos de partida, no la última palabra).
2. Por cada hallazgo real, registra: categoría, severidad (Crítico / Alto / Medio / Bajo / Info), archivo:línea, por qué es un problema, y una corrección concreta.
3. Si un punto del checklist está bien cubierto, no lo reportes como hallazgo — solo cuenta como verificado. El reporte final debe listar únicamente lo que requiere atención, no un inventario de todo lo revisado.
4. Cierra con un resumen de 3-5 líneas: qué tan expuesto está el sitio hoy y cuál sería el primer arreglo si solo hay tiempo para uno.
5. No apliques cambios automáticamente. Si el usuario pide arreglar algo del reporte, trátalo como cualquier cambio de código normal (confirmar antes de tocar RLS, políticas de Supabase, o headers en producción).

Sé exhaustivo: para cada categoría, piensa como atacante (qué input controlo, qué endpoint puedo golpear repetidamente, qué pasa si mando algo que no se esperaba) antes de descartarla como cubierta.

## Categorías

### 1. Cabeceras HTTP, CSP y clickjacking
Referencia: [middleware.ts](web/src/middleware.ts). Verificar que `aplicarCabecerasSeguridad` se siga aplicando a toda respuesta (HTML y no-HTML); que `script-src` no incluya `'unsafe-inline'` sin nonce ni `'unsafe-eval'`; que `ORIGENES_IMAGEN` ([cdn.ts](web/src/lib/cdn.ts)) refleje exactamente los hosts desde donde se sirven imágenes (un origen de más en `img-src` es un canal de exfiltración); que `X-Frame-Options: DENY` y `frame-ancestors 'none'` sigan presentes (clickjacking); que HSTS solo se envíe en `PROD`; y que no se haya reintroducido un `style-src-attr 'unsafe-inline'` más permisivo de lo necesario.

### 2. Autenticación y gestión de sesión
Referencia: [middleware.ts](web/src/middleware.ts), `web/src/lib/auth/servidor.ts`, `web/src/pages/api/auth/*`. Cubrir:
- **Cookies de sesión**: flags `HttpOnly`, `Secure` y `SameSite` correctos (las setea `@supabase/ssr`; confirmar que no se sobrescriban en algún lado con valores más laxos).
- **OAuth / magic link** ([callback.ts](web/src/pages/api/auth/callback.ts)): `exchangeCodeForSession` no reintenta ni cachea el `code` (un `code` es de un solo uso; replay debería fallar), y `volver`/`next` pasa por `rutaInterna` — confirmar que esa función rechaza URLs absolutas y protocolos `javascript:`/`data:` (open redirect).
- **Enumeración de usuarios**: mensajes de error de `entrar.ts`/`registro.ts`/`magic-link.ts` no deben revelar si un email existe o no, ni responder en tiempos claramente distintos según el caso (timing attack de enumeración).
- **Fuerza bruta de login**: sin rate limit propio, ¿hay algo (Supabase Auth, Vercel) limitando intentos de contraseña?
- **Fijación de sesión**: la cookie de sesión se regenera al iniciar sesión, no se reutiliza una preexistente de un visitante anónimo.
- **JWT**: el rol viaja en `app_metadata` dentro del JWT firmado por Supabase — confirmar que ningún endpoint confíe en un rol enviado por el cliente (body, header, query) en vez de leerlo del JWT/sesión ya validada.

### 3. Autorización, IDOR y escalación de privilegios
Referencia: `web/src/pages/api/publicacion/[id]*`, `web/src/pages/api/moderacion/[id].ts`, `web/src/pages/api/cuenta/*`. Para cada endpoint con un `[id]` en la ruta, verificar explícitamente: ¿qué impide que el usuario A mande el `id` de un recurso del usuario B? (IDOR clásico). [moderacion/[id].ts](web/src/pages/api/moderacion/%5Bid%5D.ts) ya repite el chequeo de rol admin aunque el middleware lo cubre — ese patrón de "defensa en profundidad" debería estar también en `cuenta/eliminar.ts`, `cuenta/perfil.ts` y en las acciones sobre `publicacion/[id]` (editar/despublicar solo el dueño o un admin). Señalar cualquier endpoint que confíe únicamente en el middleware para autorización a nivel de objeto (el middleware solo sabe la ruta, no de quién es el recurso).

### 4. Cliente Supabase con `service_role`
Referencia: [client.ts](web/src/lib/db/client.ts). Este cliente usa `SUPABASE_SERVICE_KEY`, que **bypassea RLS por completo**. Cualquier código que importe `supabase` desde aquí debe aplicar su propia verificación de autorización (dueño del recurso, rol admin, etc.) antes de leer o escribir — RLS no lo va a frenar. Revisar cada uso en `web/src/pages/api/**` y `web/src/lib/publicaciones/*`, y confirmar que el filtro de "quién puede ver/tocar qué" está en el código de la ruta. Verificar también que esta clave nunca llegue a un componente que corra en el cliente (bundle del navegador) ni a un log.

### 5. Políticas RLS y Storage en Supabase
Referencia: `supabase/*.sql`. Verificar que toda tabla y todo bucket de Storage con datos de usuario tenga RLS habilitado y políticas explícitas (no solo `storage.objects`); que `insert`/`update`/`delete` de fotos de particulares exijan ser el dueño de la publicación; que no exista una policy con `USING (true)` sin justificación documentada; y que las policies de `select` no expongan columnas sensibles (emails, teléfonos de otros usuarios) a través de una vista o join demasiado permisivo.

### 6. Inyección — XSS, SQL, comandos, cabeceras
- **XSS almacenado/reflejado**: [sanitizar.ts](web/src/lib/sanitizar.ts) — `escaparHtml` debe aplicarse a todo dato de usuario (o de terceros, ver categoría 7) antes de interpolarse en HTML/email; buscar cualquier `set:html` de Astro o interpolación directa en `.astro` que reciba texto no escapado.
- **XSS vía atributos/URLs**: enlaces `tel:`/`whatsapp:` construidos desde `normalizarTelefonoCL` — confirmar que no admiten inyectar otro esquema (`javascript:`).
- **SQL injection**: el ORM (SQLAlchemy) y el cliente de Supabase parametrizan por defecto; buscar puntualmente cualquier `rpc()`, query cruda o f-string que arme SQL con input de usuario sin parámetros (la función `registrar_solicitud_contacto` en [contacto.ts](web/src/pages/api/contacto.ts) usa parámetros nombrados — ese es el patrón correcto a exigir en cualquier `rpc` nuevo).
- **Command injection**: buscar `subprocess`, `os.system`, `eval`, `exec` en `src/carflip` que reciban datos scrapeados o de configuración externa.
- **Inyección de cabeceras de correo (CRLF)**: [contacto.ts](web/src/pages/api/contacto.ts) usa la API JSON de Resend (no SMTP crudo), lo que mitiga la inyección clásica de cabeceras — confirmar igual que `email`/`nombre` no puedan romper la estructura JSON o colarse en el `subject` sin pasar por `EMAIL_RE`/`NOMBRE_RE`.
- **Log injection**: cualquier `console.log`/`loguru` que incluya input de usuario tal cual puede permitir forjar líneas de log (CRLF); revisar que no se logguee texto de usuario sin sanear en rutas de alto volumen.

### 7. Contenido de terceros no confiable (el dato scrapeado es input hostil)
Referencia: `src/carflip/scrapers/**`. CarFlip es un agregador: títulos, descripciones y precios vienen de portales externos (Yapo, AutoCosmos, etc.) que no controla CarFlip. Tratar ese contenido como **input de usuario no confiable**, igual que un formulario:
- ¿El HTML/texto scrapeado se sanea/escapa antes de guardarse y de renderizarse en las páginas de publicación? Un título de aviso con `<script>` o `javascript:` en un link debería neutralizarse igual que un campo de formulario.
- ¿Las URLs de imágenes o de "ver publicación original" que vienen del scraper pasan por el mismo allow-list de orígenes que `resolverUrlImagen`, o se confía ciegamente en el host de origen?
- ¿Un portal de origen podría inyectar datos que rompan la lógica de negocio (precio negativo, fecha inválida, patente con caracteres especiales) y llegar así hasta la UI o hasta `patente.ts`?

### 8. CSRF
Referencia: endpoints `POST` en `web/src/pages/api/**` que actúan sobre sesión de cookie (moderación, cuenta, reportar, publicar). Con `SameSite=Lax` (default de Supabase SSR) las peticiones cross-site tipo formulario simple ya quedan mitigadas para la mayoría de casos, pero confirmar: ¿algún endpoint de estado (despublicar, eliminar cuenta, cambiar rol) acepta también `GET`, lo que lo haría explotable con solo un `<img>`/link? ¿Se valida el header `Origin`/`Referer` en las acciones más sensibles (eliminar cuenta, moderación) como capa adicional?

### 9. SSRF y redirects abiertos
Referencia: [enlaces.ts](web/src/lib/enlaces.ts), [cdn.ts](web/src/lib/cdn.ts), `web/src/lib/auth/servidor.ts` (`rutaInterna`), scraper en `src/carflip`.
- **Web (Astro)**: ningún fetch/redirect del lado servidor debe construirse desde una URL controlada por el usuario sin validarla contra un allow-list (mismo patrón que `resolverUrlImagen`); revisar `rutaInterna` para el mismo problema en redirects de login.
- **Scraper (Playwright/httpx)**: visita URLs de portales externos por diseño, pero si alguna de esas URLs (o un redirect servido por el portal) pudiera apuntar a una IP interna o al endpoint de metadata de la nube (`169.254.169.254`), el scraper podría usarse como proxy SSRF hacia infraestructura interna. Verificar si hay alguna restricción de red/DNS para el proceso de scraping, o si corre con acceso irrestricto a la red del host/contenedor.

### 10. Manejo de archivos e imágenes
Referencia: `web/src/pages/api/publicacion/[id]/fotos.ts`, `supabase/storage_avisos_particulares.sql`, `src/carflip/scrapers/image_utils.py`.
- Límites de tamaño y validación de tipo MIME real (no solo la extensión) en toda subida.
- **Decompression bomb**: `Image.open()` en [image_utils.py](src/carflip/scrapers/image_utils.py) no fija `Image.MAX_IMAGE_PIXELS` explícitamente — una imagen con dimensiones enormes (bomba de descompresión) puede agotar memoria/CPU al procesarse; confirmar si Pillow igual la frena por defecto o si conviene un límite explícito.
- **Path traversal**: cualquier construcción de ruta de archivo a partir de un nombre o clave que venga del usuario o del portal scrapeado (`../` en el nombre) antes de escribir a disco o a Storage.
- Políticas de Storage que limiten quién puede subir/borrar cada foto (ver categoría 5).

### 11. Rate limiting, abuso y denegación de servicio
Referencia: `web/src/pages/api/auth/*`, [contacto.ts](web/src/pages/api/contacto.ts), `web/src/pages/api/publicacion/[id]/reportar.ts`, `web/src/pages/api/publicacion/[id]/fotos.ts`.
- [contacto.ts](web/src/pages/api/contacto.ts) ya tiene honeypot + rate limit serializado por IP vía RPC — usar ese patrón como referencia de "endpoint bien protegido" y señalar cuáles otros endpoints de escritura (reportar, subir fotos, registro, magic-link) carecen de un control equivalente.
- **ReDoS**: revisar los regex de [sanitizar.ts](web/src/lib/sanitizar.ts), `patente.ts` y `contacto.ts` (`EMAIL_RE`, `NOMBRE_RE`) por patrones con backtracking catastrófico ante input largo y adversarial.
- **Denial of wallet**: subida de fotos o reintentos de scraping/pipeline de imágenes que generen costo variable (Storage, R2, cómputo de conversión) sin límite por usuario/IP.
- **Race conditions**: acciones concurrentes sobre el mismo recurso (dos reportes o dos moderaciones simultáneas sobre el mismo aviso, doble submit de un formulario) que puedan dejar datos inconsistentes.

### 12. Exposición de información en errores y respuestas
Referencia: páginas `403`/`500`, manejo de excepciones en `web/src/pages/api/**`. Los errores no deben filtrar stack traces, rutas del sistema de archivos, ni detalles de la query SQL al cliente en producción. Confirmar que ninguna respuesta JSON de error devuelva el objeto de error crudo de Supabase/Postgres (puede incluir nombres de tabla/columna internos).

### 13. Secretos y variables de entorno
Referencia: `.env` (raíz, único para web y scraper), `.gitignore`. Verificar que `.env*` siga ignorado en git, que las variables públicas usen el prefijo `PUBLIC_` de Astro y las privadas (`SUPABASE_SERVICE_KEY`, credenciales AWS/R2, `RESEND_API_KEY`) nunca se expongan al cliente ni aparezcan en logs, que no haya secretos hardcodeados en el repo (grep por claves, tokens, contraseñas), y que el fallback de `RATE_SALT` a `SUPABASE_SERVICE_KEY` en [contacto.ts](web/src/pages/api/contacto.ts) siga siendo intencional y no una fuga accidental si se define `CONTACT_RATE_SALT` en algún entorno.

### 14. Dependencias y cadena de suministro
Referencia: `web/package.json` + `package-lock.json`, `pyproject.toml` + `uv.lock`. Correr o revisar el equivalente a `npm audit --production` y un chequeo de CVEs conocidas en las dependencias Python (httpx, playwright, sqlalchemy, pillow, etc.). Confirmar que los lockfiles estén commiteados, que no haya scripts `postinstall` sospechosos en dependencias nuevas, y que no se hayan agregado paquetes sin uso real (superficie de ataque innecesaria).

### 15. Automatización de navegador (Playwright) contra sitios hostiles
Referencia: `src/carflip/scrapers/**`. El scraper ejecuta un navegador real contra páginas que no controla. Un portal de origen comprometido o malicioso podría intentar explotar el propio Chromium/Playwright, forzar descargas, o abrir popups/redirects encadenados. Verificar que el contexto de Playwright deshabilite descargas automáticas no esperadas, no reutilice una sesión/perfil con cookies sensibles, y corra con los permisos mínimos (sin acceso a filesystem del host más allá de lo necesario).

### 16. Terceros embebidos en el sitio
Referencia: `@vercel/analytics`, Google OAuth. Confirmar que los scripts de terceros cargados en el sitio sean solo los declarados en la CSP (`script-src`), que Analytics no envíe datos personales innecesarios, y que el flujo de Google OAuth valide el `state`/`nonce` para evitar CSRF sobre el propio login (esto lo maneja `@supabase/ssr`, pero vale confirmar que no se haya customizado de forma insegura).

### 17. Lógica de negocio
Referencia: `web/src/lib/publicaciones/*`, `web/src/pages/api/publicacion/**`. Pensar en abuso específico del dominio: ¿puede un particular editar precio/estado de una publicación ajena cambiando el `id`? ¿Puede reportar su propia publicación repetidamente para manipular las colas de moderación? ¿Hay límite a cuántas publicaciones puede crear un mismo usuario/IP (spam de listados falsos)? ¿El detector de "deals" (`src/carflip/deals/`) podría ser engañado por un portal que publique precios falsos para aparecer como oferta destacada?

### 18. Infraestructura (Docker, logs, backups)
Referencia: `docker/Dockerfile`, `docker/docker-compose.yml`, `logs/`, `alembic/`. Verificar que el contenedor no corra como root, que no haya secretos horneados en la imagen (deben inyectarse por env en runtime), que `logs/` no termine con PII o tokens en texto plano, y que las migraciones de Alembic no queden expuestas ni se puedan disparar desde un endpoint público.

### 19. CORS
Referencia: endpoints en `web/src/pages/api/`. Confirmar que ninguna respuesta agregue `Access-Control-Allow-Origin: *` u orígenes de terceros sin necesidad — el sitio no debería exponer su API a otros dominios salvo que sea explícitamente necesario.
