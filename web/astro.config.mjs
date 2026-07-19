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
    sitemap({ filter: (page) => !page.includes('/dashboard') }),
  ],
  vite: {
    plugins: [tailwindcss()],
  },
});
