/// <reference types="astro/client" />
interface ImportMetaEnv {
  readonly DATABASE_URL: string;
  readonly USE_SSL: string;
  readonly CDN_BASE_URL?: string;
}
