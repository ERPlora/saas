// Browser checks of the public web (spec §6 and §9, `tests/e2e/`): Ioan's Chrome, headless by default
// (Ioan, 2026-10-14); a visible, slowed-down window only when a run asks for it (`E2E_HEADED=1`,
// `pnpm e2e:headed`), never in CI.
//
// It drives a production-like SaaS of its own: DEBUG off (the public CSP as production serves it,
// no Vite dev server), the build of `pnpm build` (run it first: the manifest must hold
// `frontend/public.ts`), static files served by `runserver --insecure`, on 127.0.0.1:8011 so it never
// collides with the dev server on :8001. `globalSetup` first stops the run if the local database of
// `.env` has unapplied migrations (it never migrates it: sessions share it), then seeds the app the
// specs open and removes it at the end (store_docs_seed.py).
//
// Each run writes its traces and failure screenshots into `.artifacts/test-results/<run id>/`, and the
// specs their evidence into `.artifacts/` (both ignored by git).
//
// Two projects (README.md): `public`, the specs above against that server, and `panel`, the panel's
// specs (`panel/`) against the dev server on :8001 (panel/project.ts). `pnpm e2e` runs both and
// `--project=public|panel` one, headless; `pnpm e2e:headed` the same in a visible Chrome; `pnpm e2e:ci`
// (CI=1) is the CI run.
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '@playwright/test';

import { panelProject, panelServers } from './panel/project';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');
const PORT = Number(process.env.E2E_PORT ?? 8011);
export const BASE_URL = `http://127.0.0.1:${PORT}`;

process.env.PW_RUN_ID ??= new Date().toISOString().replace(/[:.]/g, '-');

/** Milliseconds between the steps of a visible run, so a person can follow it. */
const SLOW_MO = 150;

/**
 * The browser's window for a run with `env`: headless and at full speed by default (Ioan, 2026-10-14);
 * a visible Chrome, slowed down, only with `E2E_HEADED=1`. CI never opens one, whatever it asks.
 */
export function browserWindow(env: Record<string, string | undefined>): { headless: boolean; slowMo: number } {
  const headed = env.E2E_HEADED === '1' && !env.CI;
  return { headless: !headed, slowMo: headed ? SLOW_MO : 0 };
}

const WINDOW = browserWindow(process.env);

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: join(HERE, '.artifacts', 'test-results', process.env.PW_RUN_ID),
  globalSetup: join(HERE, 'global-setup.ts'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    channel: 'chrome',
    headless: WINDOW.headless,
    launchOptions: { slowMo: WINDOW.slowMo },
    viewport: { width: 1280, height: 860 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'public', testIgnore: 'panel/**' }, panelProject],
  webServer: [
    {
      command: `uv run python manage.py runserver 127.0.0.1:${PORT} --novite --insecure --noreload`,
      cwd: SAAS_DIR,
      url: `${BASE_URL}/robots.txt`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        DEBUG: 'False',
        // Production refuses to start without a key; this one only signs this local, throwaway server.
        SECRET_KEY: 'e2e-local-only-not-a-secret',
        // Production refuses to start without it either (fiscal/): a valid Fernet key that encrypts nothing here.
        FISCAL_DOCUMENTS_KEY: 'ZTJlLWxvY2FsLW9ubHktbm90LWEtc2VjcmV0LWtleSE=',
        ALLOWED_HOSTS: '127.0.0.1,localhost',
      },
    },
    ...panelServers(SAAS_DIR),
  ],
});
