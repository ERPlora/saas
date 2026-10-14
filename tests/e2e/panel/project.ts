// The panel's project of the e2e (`tests/e2e/panel/`, README.md): the SPA of erplora.com as
// `manage.py runserver` serves it in development, its assets from Vite on :5174. DEBUG on: the SPA's dev
// shell, and `demo_seed` refuses to run without it.
//
// Django is the panel's own, on :8012, never reused: another session's runserver on :8001 reloads on
// every `.py` another session saves (a run lost its server mid-spec) and calls whatever Hub runs on
// :8000, whose answers (a refusal, a database provisioned for a throwaway business) are not the
// specs'. Here it runs without the autoreloader and with `HUB_INTERNAL_URL` at a port nobody listens
// on: every call to the Hub stays pending, as when the Hub is away, and the specs play the Hub (its
// signed `ready` callback). Vite is reused when it is up (it only serves the files). Playwright stops
// what it started at the end, never what it reused.
import type { PlaywrightTestConfig, Project } from '@playwright/test';

export const PANEL_URL = 'http://localhost:8012';

type WebServer = Exclude<NonNullable<PlaywrightTestConfig['webServer']>, unknown[]>;

export const panelProject: Project = {
  name: 'panel',
  testDir: 'panel',
  // English, whatever the machine's language: the specs read the English texts.
  use: { baseURL: PANEL_URL, locale: 'en-US' },
};

/** Django on :8012 and Vite on :5174, from saas-next/ (`saasDir`). */
export function panelServers(saasDir: string): WebServer[] {
  return [
    {
      name: 'panel-django',
      command: 'uv run python manage.py runserver 127.0.0.1:8012 --novite --noreload',
      cwd: saasDir,
      // /healthz answers on any Host and never touches the database (base/health.py).
      url: 'http://127.0.0.1:8012/healthz',
      reuseExistingServer: false,
      timeout: 120_000,
      // Port 9 (discard): nothing answers, so every call to the Hub fails fast and stays pending.
      env: { DEBUG: 'True', HUB_INTERNAL_URL: 'http://127.0.0.1:9' },
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
