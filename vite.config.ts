// Vite of saas-next (mirror of hub-next's). A contract with Django (`packages/live/live/spa.py`,
// `LIVE["spa"]` in `config/settings.py`): with DEBUG the shell loads
// `http://localhost:5174/static/spa/@vite/client` and `…/static/spa/frontend/main.ts` (Vite applies
// `base` in dev too); in production Django reads `frontend/dist/.vite/manifest.json` and links
// `/static/spa/assets/…` (WhiteNoise). `manage.py runserver` starts this dev server (`LIVE["vite"]`);
// `--novite` skips it. Port 5174: hub-next's dev server owns 5173 and both run at once.
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { erploraVite } from '@erplora/ui/vite';
import { defineConfig } from 'vitest/config';

const DEV_HOST = 'localhost';
const DEV_PORT = 5174;

/**
 * The apps with a `frontend/`: at the project root, next to `base/` (no `apps/`, PLAN §20.2). No
 * `marketplace` (round 16): the app catalogue is `apps`, and neither it nor `public` has a frontend.
 */
export const FRONTEND_APPS = ['accounts', 'hubs', 'billing'];

export default defineConfig({
  // From the string: under happy-dom (tests) the global `URL` is not Node's.
  root: dirname(fileURLToPath(import.meta.url)),
  base: '/static/spa/',
  // No public directory: Vite's default, `<root>/public`, is the public web's Django app (Python and
  // tests), which `vite build` would copy into frontend/dist and serve under /static/spa/.
  publicDir: false,
  plugins: erploraVite({
    frontendSources: ['frontend/**/*.{vue,ts}', ...FRONTEND_APPS.map((app) => `${app}/frontend/**/*.{vue,ts}`)],
  }),
  build: {
    outDir: 'frontend/dist',
    emptyOutDir: true,
    manifest: '.vite/manifest.json',
    target: 'es2022',
    // The SPA (LIVE["spa"]["entry"]) and the public web's Django templates (`{% public_assets %}`).
    rollupOptions: { input: ['frontend/main.ts', 'frontend/public.ts'] },
  },
  server: {
    host: DEV_HOST,
    port: DEV_PORT,
    // Django hard-codes the port: another free one would serve a page that never loads.
    strictPort: true,
    // The page comes from `localhost:8001`: asset URLs must point back at this server.
    origin: `http://${DEV_HOST}:${DEV_PORT}`,
    hmr: { host: DEV_HOST, port: DEV_PORT },
  },
  test: {
    environment: 'happy-dom',
    // happy-dom with the browser behaviour Ionic relies on (vitest.setup.ts).
    setupFiles: ['./vitest.setup.ts'],
    include: [
      'frontend/**/*.test.ts',
      ...FRONTEND_APPS.map((app) => `${app}/frontend/**/*.test.ts`),
      'vite.config.test.ts',
      'eslint.config.test.ts',
    ],
    // Vitest's default `exclude` drops every `vite.config.*` and `eslint.config.*`.
    exclude: ['**/node_modules/**', '**/dist/**'],
  },
});
