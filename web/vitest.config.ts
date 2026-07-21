import { fileURLToPath } from 'node:url';

import { defineConfig } from 'vitest/config';

// Los alias replican los `paths` de tsconfig.json: Astro los resuelve en build,
// pero Vitest no lee tsconfig, y sin esto falla cualquier módulo bajo prueba que
// importe con `@lib/…`.
const rutaDe = (relativa: string) => fileURLToPath(new URL(relativa, import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      '@lib': rutaDe('./src/lib'),
      '@components': rutaDe('./src/components'),
      '@layouts': rutaDe('./src/layouts'),
    },
  },
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
  },
});
