import { fileURLToPath } from 'node:url';

import { getViteConfig } from 'astro/config';

// `getViteConfig` levanta el pipeline de Astro dentro de Vitest: sin él no se
// pueden importar componentes `.astro` ni el módulo virtual `astro:middleware`.
const rutaDe = (relativa: string) => fileURLToPath(new URL(relativa, import.meta.url));

export default getViteConfig({
  // Los alias replican los `paths` de tsconfig.json: Astro los resuelve en build,
  // pero Vitest no lee tsconfig, y sin esto falla cualquier módulo bajo prueba que
  // importe con `@lib/…`.
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
    // El componente de Vercel Analytics se publica como TypeScript sin compilar y
    // Node no puede quitarle los tipos dentro de node_modules: inlinearlo hace que
    // lo transforme Vite. Lo arrastra el layout Base, del que cuelgan las páginas.
    server: { deps: { inline: ['@vercel/analytics'] } },
  },
});
