// The panel's project of the e2e (`tests/e2e/panel/`, README.md): the SPA of erplora.com as
// `manage.py runserver` serves it in development, its assets from Vite on :5174. DEBUG on: the SPA's dev
// shell, and `demo_seed` refuses to run without it.
//
// Django is the panel's own, on :8012, never reused: another session's runserver on :8001 reloads on
// every `.py` another session saves (a run lost its server mid-spec) and calls whatever Hub runs on
// :8000, whose answers (a refusal, a database provisioned for a throwaway business) are not the
// specs'. Here it runs without the autoreloader and with `HUB_INTERNAL_URL` at a port nobody listens
// on: every call to the Hub stays pending, as when the Hub is away, and the specs play the Hub (its
// signed `ready` callback; `startHubDouble` of fixtures.ts listens there while a spec needs to see
// what the SaaS sends). Every mail it sends lands in a file of `PANEL_MAIL_DIR` (Django's file
// backend), where the specs read the links (`waitForMail`). Vite is reused when it is up (it only
// serves the files). Playwright stops what it started at the end, never what it reused.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { PlaywrightTestConfig, Project } from '@playwright/test';

export const PANEL_URL = 'http://localhost:8012';

/** Where the panel's Django writes the mails it sends (`tests/e2e/.artifacts/panel/mail/`, ignored by git). */
export const PANEL_MAIL_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '.artifacts', 'panel', 'mail');

/**
 * The Hub's `/internal` as the panel's Django calls it (`HUB_INTERNAL_URL`). Nobody listens there,
 * so every call fails at once and stays owed, as with the Hub away, except while a spec plays the
 * Hub on it (`startHubDouble`).
 */
export const HUB_DOUBLE_PORT = 8019;

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
      env: {
        DEBUG: 'True',
        HUB_INTERNAL_URL: `http://127.0.0.1:${HUB_DOUBLE_PORT}`,
        EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
        EMAIL_FILE_PATH: PANEL_MAIL_DIR,
      },
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
