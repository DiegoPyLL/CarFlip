import { type ChildProcess, spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { createRequire } from 'node:module';
import path from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

/**
 * El formulario de /contacto respondía 500 en cada envío (issue #45): el endpoint
 * devolvía `Response.redirect()`, cuyas cabeceras son inmutables, y el middleware
 * moría al escribirle las de seguridad. Los tests no lo vieron porque probaban al
 * handler y al middleware por separado, y por separado los dos estaban bien: el
 * fallo solo existe cuando la respuesta de uno pasa por el otro.
 *
 * Este levanta el servidor de verdad y hace el POST por HTTP, que es la única
 * forma de recorrer el camino completo. Solo ejercita lo que retorna antes de
 * llamar a Resend —honeypot y datos inválidos, que son igualmente los que daban
 * 500—: el `envDir: '../'` de `astro.config.mjs` carga el .env real, así que un
 * envío válido acá mandaría un correo de verdad y gastaría cuota. Ese caso vive
 * en `tests/formularios/contacto.test.ts`, con `fetch` doblado.
 */

const astroBin = path.join(
  path.dirname(createRequire(import.meta.url).resolve('astro/package.json')),
  'bin/astro.mjs',
);

/** Puerto libre pedido al sistema: con uno fijo, otro servidor ocupándolo desvía las pruebas. */
function puertoLibre(): Promise<number> {
  return new Promise((resolver, rechazar) => {
    const sonda = createServer();
    sonda.once('error', rechazar);
    sonda.listen(0, '127.0.0.1', () => {
      const { port } = sonda.address() as { port: number };
      sonda.close(() => resolver(port));
    });
  });
}

/**
 * Espera a que la home responda 200. No basta con que `fetch` resuelva: Vite
 * acepta conexiones antes de montar el router de Astro, y en esa ventana todas
 * las rutas —incluida /api/contacto— devuelven 404 y las pruebas medirían aire.
 */
async function esperarListo(origen: string, salida: () => string, limiteMs = 90_000): Promise<void> {
  const limite = Date.now() + limiteMs;
  for (;;) {
    let ultimo = '';
    try {
      const r = await fetch(`${origen}/`);
      if (r.status === 200) return;
      ultimo = `status ${r.status}: ${(await r.text()).slice(0, 300)}`;
    } catch (error) {
      ultimo = `sin conexión: ${error}`;
    }
    if (Date.now() > limite) {
      throw new Error(`El servidor de ${origen} no levantó a tiempo.\n${ultimo}\n${salida()}`);
    }
    await new Promise((seguir) => setTimeout(seguir, 250));
  }
}

let servidor: ChildProcess;
let origen = '';

beforeAll(async () => {
  const puerto = await puertoLibre();
  origen = `http://localhost:${puerto}`;
  // `ASTRO_DEV_BACKGROUND` apaga la detección de entorno de agente, que si no
  // demoniza el proceso: el hijo dejaría de ser el servidor y `kill` no cerraría
  // nada. Es la misma variable con la que Astro arranca sus servidores de fondo.
  const entorno: NodeJS.ProcessEnv = { ...process.env, ASTRO_DEV_BACKGROUND: '1' };
  // El plugin `astro:server` se desactiva entero si ve `VITEST`, para que los
  // tests que usan `getViteConfig` no levanten un sitio sin querer. Este servidor
  // es otro proceso, de verdad, así que la marca no le corresponde: heredarla deja
  // a Vite respondiendo 404 a todo, y las pruebas medirían aire.
  delete entorno.VITEST;

  // `--ignore-lock` mantiene este servidor fuera del lock del proyecto, para que no
  // choque con un `npm run dev` abierto ni lo dé por suyo un `astro dev stop`.
  servidor = spawn(process.execPath, [astroBin, 'dev', '--port', String(puerto), '--ignore-lock'], {
    cwd: process.cwd(),
    env: entorno,
  });

  // La salida del servidor se guarda para que un arranque fallido diga por qué,
  // en vez de dejar solo un timeout mudo.
  let salida = '';
  servidor.stdout?.on('data', (trozo) => (salida += trozo));
  servidor.stderr?.on('data', (trozo) => (salida += trozo));

  await esperarListo(origen, () => salida);
}, 120_000);

afterAll(() => {
  servidor?.kill();
});

/**
 * `redirect: 'manual'` para mirar el 303 en vez de seguirlo, y `origin` propio
 * porque `security.checkOrigin` de Astro responde 403 a los POST de formulario
 * que llegan de otro sitio.
 */
function enviar(campos: Record<string, string>, origin = origen): Promise<Response> {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries(campos)) datos.append(clave, valor);
  return fetch(`${origen}/api/contacto`, {
    method: 'POST',
    body: datos,
    headers: { origin },
    redirect: 'manual',
  });
}

const INVALIDOS = { nombre: '', email: 'no-es-un-email', mensaje: '' };

describe('POST /api/contacto por HTTP', () => {
  it('redirige con 303 en vez de romperse, cuando los datos son inválidos', async () => {
    const respuesta = await enviar(INVALIDOS);

    expect(respuesta.status).toBe(303);
    expect(respuesta.headers.get('location')).toBe('/contacto?error=1');
  });

  it('descarta el honeypot con la misma respuesta que un envío bueno', async () => {
    const respuesta = await enviar({
      nombre: 'Bot',
      email: 'bot@example.com',
      mensaje: 'spam',
      web: 'http://spam.example',
    });

    expect(respuesta.status).toBe(303);
    expect(respuesta.headers.get('location')).toBe('/contacto?enviado=1');
  });

  it('la redirección sale con las cabeceras de seguridad, no solo sin caerse', async () => {
    const respuesta = await enviar(INVALIDOS);

    expect(respuesta.headers.get('x-content-type-options')).toBe('nosniff');
    expect(respuesta.headers.get('referrer-policy')).toBe('strict-origin-when-cross-origin');
    expect(respuesta.headers.get('x-frame-options')).toBe('DENY');
    expect(respuesta.headers.get('content-security-policy')).toContain("default-src 'none'");
  });

  it('rechaza el envío que llega desde otro origen', async () => {
    const respuesta = await enviar(INVALIDOS, 'https://evil.example');

    expect(respuesta.status).toBe(403);
  });
});
