import { defineConfig } from 'astro/config';
import vercel from '@astrojs/vercel';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://carflip.cl',
  output: 'server',
  adapter: vercel({ maxDuration: 10 }),
  // El default 'jsx' de Astro 7 colapsa espacios entre elementos inline y altera el texto renderizado.
  compressHTML: true,
  // El default 'auto' incrusta las hojas menores a 4 kB en un <style>, que la CSP
  // de `middleware.ts` bloquea: `style-src` es 'self', sin 'unsafe-inline'.
  build: { inlineStylesheets: 'never' },
  // `@astrojs/sitemap` nombra su índice `sitemap-index.xml` y no es configurable,
  // pero /sitemap.xml es la ruta que adivinan tanto las personas como las
  // herramientas de terceros. Un 301 evita que se topen con el 404.
  redirects: { '/sitemap.xml': { status: 301, destination: '/sitemap-index.xml' } },
  integrations: [
    // Las páginas de sesión, de cuenta y de error son `noindex`: listarlas en el
    // sitemap sería contradictorio para los rastreadores.
    sitemap({
      filter: (page) =>
        !['/dashboard', '/entrar', '/registro', '/recuperar-contrasena', '/cuenta', '/403', '/500'].some(
          (r) => page.includes(r),
        ),
      // Los sitemaps de avisos y marcas son endpoints SSR, invisibles para la
      // integración. Declararlos aquí los suma al sitemap index, de modo que un
      // solo archivo lleve a todo el catálogo.
      customSitemaps: [
        'https://carflip.cl/sitemap-avisos.xml',
        'https://carflip.cl/sitemap-marcas.xml',
      ],
      // Con el `trailingSlash: 'ignore'` de Astro la integración emite `/avisos/`,
      // pero `Base.astro` declara el canonical sin barra: proponerle a Google la
      // variante que la propia página descarta. La raíz sí la conserva.
      serialize: (item) => ({ ...item, url: item.url.replace(/(.)\/$/, '$1') }),
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    // Único .env del proyecto: vive en la raíz del repo, no en web/, para no
    // duplicarlo con el que usa el backend Python.
    envDir: '../',
    // Astro incrusta los chunks de script menores a 4 kB como `<script>` inline
    // sin nonce, y el `script-src` de `middleware.ts` no admite inline sin él:
    // en producción no se ejecutaba ninguno. Como archivo los cubre `'self'`.
    // `undefined` para el resto conserva el default de Vite.
    build: { assetsInlineLimit: (ruta) => (ruta.endsWith('.js') ? false : undefined) },
  },
});
