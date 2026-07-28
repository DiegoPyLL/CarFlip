#!/usr/bin/env node
// Guardarraíl de build: falla si Astro incrustó algún `<script>` en el HTML.
//
// Astro empaqueta como inline los chunks de script menores al `assetsInlineLimit`
// de Vite, y los emite sin nonce (`renderScript` en astro/dist/runtime/server).
// El `script-src 'self' 'nonce-…'` de `src/middleware.ts` no admite inline sin
// nonce, así que un script incrustado no se ejecuta en producción —y en local sí,
// porque Vite lo sirve como módulo con `src`. Es un fallo invisible hasta el
// deploy: lo cierra `assetsInlineLimit` en `astro.config.mjs`, y esto lo vigila.
//
// Los tests de `tests/paginas/cabeceras-seguridad.test.ts` cubren la otra mitad:
// que la política sea correcta. Esta cubre que el HTML emitido la respete.

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// El manifiesto serializado del adaptador de Vercel. `plugin-manifest` siempre
// escribe la clave, vacía o no, así que basta con buscarla literalmente vacía.
const MANIFIESTO = fileURLToPath(new URL('../.vercel/output/_functions/entry.mjs', import.meta.url));
const VACIO = '"inlinedScripts":[]';

async function main() {
  let contenido;
  try {
    contenido = await readFile(MANIFIESTO, 'utf8');
  } catch {
    throw new Error(`No se encontró el manifiesto del build en ${MANIFIESTO}. Corre "npm run build".`);
  }

  if (contenido.includes(VACIO)) return;

  const origenes = [...new Set(
    [...contenido.matchAll(/([^"/\\]+\.astro)\?astro&type=script/g)].map((m) => m[1]),
  )];

  console.error('Astro incrustó scripts inline en el HTML; la CSP de src/middleware.ts los bloqueará:');
  for (const origen of origenes) console.error(`  - ${origen}`);
  console.error('\nRevisa "vite.build.assetsInlineLimit" en astro.config.mjs.');
  process.exitCode = 1;
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
