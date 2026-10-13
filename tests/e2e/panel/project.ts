// The panel's project of the e2e (`tests/e2e/panel/`, README.md): the SPA of erplora.com as
// `manage.py runserver` serves it in development, on localhost:8001, its assets from Vite on :5174.
// DEBUG on: the SPA's dev shell, and `demo_seed` refuses to run without it.
//
// Two servers, each reused when it is already up (another session's runserver, or Ioan's): Django
// without Vite and without the autoreloader, since every `.py` another session saves would restart
// it mid-run, and Vite on its own, so the run waits until both answer (Django is up before Vite, and
// a page whose module scripts point at a Vite not listening yet stays blank). Playwright stops what it
// started at the end, never what it reused.
import type { PlaywrightTestConfig, Project } from '@playwright/test';

export const PANEL_URL = 'http://localhost:8001';

type WebServer = Exclude<NonNullable<PlaywrightTestConfig['webServer']>, unknown[]>;

export const panelProject: Project = {
  name: 'panel',
  testDir: 'panel',
  // English, whatever the machine's language: the specs read the English texts.
  use: { baseURL: PANEL_URL, locale: 'en-US' },
};

/** Django on :8001 and Vite on :5174, from saas-next/ (`saasDir`). */
export function panelServers(saasDir: string): WebServer[] {
  return [
    {
      name: 'panel-django',
      command: 'uv run python manage.py runserver 127.0.0.1:8001 --novite --noreload',
      cwd: saasDir,
      // /healthz answers on any Host and never touches the database (base/health.py).
      url: 'http://127.0.0.1:8001/healthz',
      reuseExistingServer: true,
      timeout: 120_000,
      env: { DEBUG: 'True' },
    },
    {
      name: 'panel-vite',
      command: 'pnpm run dev',
      cwd: saasDir,
      // What the dev shell loads first (`live.spa`, LIVE["spa"] in config/settings.py).
      url: 'http://localhost:5174/static/spa/@vite/client',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ];
}
