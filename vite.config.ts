// Vite of saas-next (mirror of hub-next's). A contract with Django (`packages/live/live/spa.py`,
// `LIVE["spa"]` in `config/settings.py`): with DEBUG the shell loads
// `http://localhost:5174/static/spa/@vite/client` (`VITE_DEV_PORT` moves it) and
// `…/static/spa/frontend/main.ts` (Vite applies `base` in dev too); in production Django reads
// `frontend/dist/.vite/manifest.json` and links `/static/spa/assets/…` (WhiteNoise).
// `manage.py runserver` starts this dev server (`LIVE["vite"]`); `--novite` skips it.
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { erploraVite } from '@erplora/ui/vite';
import { defineConfig } from 'vitest/config';

const ROOT = dirname(fileURLToPath(import.meta.url));
const DEV_HOST = 'localhost';
// 5174 (hub-next's dev server owns 5173 and both run at once) unless a second checkout runs beside
// another one (the e2e of a branch): Django reads the same VITE_DEV_PORT (`config/settings.py`).
const DEV_PORT_TEXT = process.env.VITE_DEV_PORT ?? '5174';
const DEV_PORT = /^\d+$/.test(DEV_PORT_TEXT) ? Number(DEV_PORT_TEXT) : 0;
if (DEV_PORT <= 0 || DEV_PORT >= 65536) {
  throw new Error(`VITE_DEV_PORT must be a TCP port, not ${JSON.stringify(DEV_PORT_TEXT)}.`);
}
/**
 * The header every dev response carries with the checkout this server serves: the panel's e2e reuses a
 * running Vite only when it is this tree's (`VITE_ROOT_HEADER` of tests/e2e/panel/project.ts).
 */
const ROOT_HEADER = 'x-erplora-vite-root';

/**
 * The apps with a `frontend/`: at the project root, next to `base/` (no `apps/`, PLAN §20.2). No
 * `marketplace` (round 16): the app catalogue is `apps`, and neither it nor `public` has a frontend.
 */
export const FRONTEND_APPS = ['accounts', 'hubs', 'billing', 'fiscal'];

export default defineConfig({
  // From the string: under happy-dom (tests) the global `URL` is not Node's.
  root: ROOT,
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
    // Django points the page at this port: another free one would serve a page that never loads.
    strictPort: true,
    // The page comes from `localhost:8001`: asset URLs must point back at this server.
    origin: `http://${DEV_HOST}:${DEV_PORT}`,
    hmr: { host: DEV_HOST, port: DEV_PORT },
    headers: { [ROOT_HEADER]: encodeURIComponent(ROOT) },
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
      // The e2e's helpers; its Playwright specs (`*.spec.ts`) run under Playwright only.
      'tests/e2e/*.test.ts',
    ],
    // Vitest's default `exclude` drops every `vite.config.*` and `eslint.config.*`.
    exclude: ['**/node_modules/**', '**/dist/**'],
  },
});
