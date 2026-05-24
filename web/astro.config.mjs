import { defineConfig } from 'astro/config';
import vercel from '@astrojs/vercel';
import tailwind from '@astrojs/tailwind';
import sitemap from '@astrojs/sitemap';

import react from '@astrojs/react';

export default defineConfig({
  output: 'server',
  adapter: vercel({ maxDuration: 10 }),
  integrations: [
    tailwind({ applyBaseStyles: true }),
    sitemap(),
    react(),
  ],
  site: 'https://carflip.vercel.app',
});