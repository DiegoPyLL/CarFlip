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
  integrations: [
    // Las páginas de sesión, de cuenta y de error son `noindex`: listarlas en el
    // sitemap sería contradictorio para los rastreadores.
    sitemap({
      filter: (page) =>
        !['/dashboard', '/entrar', '/registro', '/cuenta', '/403', '/500'].some((r) => page.includes(r)),
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    // Único .env del proyecto: vive en la raíz del repo, no en web/, para no
    // duplicarlo con el que usa el backend Python.
    envDir: '../',
  },
});
