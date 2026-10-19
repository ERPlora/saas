// The panel's project of the e2e (`tests/e2e/panel/`, README.md): the SPA of erplora.com as
// `manage.py runserver` serves it in development, its assets from Vite on :5174 (`VITE_DEV_PORT` moves it,
// for Django and Vite alike). DEBUG on: the SPA's dev shell, and `demo_seed` refuses to run without it.
//
// Django is the panel's own, on :8012, never reused: another session's runserver on :8001 reloads on
// every `.py` another session saves (a run lost its server mid-spec) and calls whatever Hub runs on
// :8000, whose answers (a refusal, a database provisioned for a throwaway business) are not the
// specs'. Here it runs without the autoreloader and with `HUB_INTERNAL_URL` at a port nobody listens
// on: every call to the Hub stays pending, as when the Hub is away, and the specs play the Hub (its
// signed `ready` callback; `startHubDouble` of fixtures.ts listens there while a spec needs to see
// what the SaaS sends). Every mail it sends lands in a file of `PANEL_MAIL_DIR` (Django's file
// backend), where the specs read the links (`waitForMail`). Vite is reused when it is up (it only
// serves the files), but only when it serves this checkout: globalSetup checks it (`assertViteOfThisTree`),
// since another tree's Vite on the port (a worker's SaaS of main) would have the specs test its frontend.
// Playwright stops what it started at the end, never what it reused.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { PlaywrightTestConfig, Project } from '@playwright/test';

import { djangoEnv } from '../django-env';

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

/**
 * Vite's port for a run with `env`: `VITE_DEV_PORT` (config/settings.py and vite.config.ts read it
 * too), 5174 when it is not exported.
 */
export function vitePort(env: Record<string, string | undefined>): number {
  const text = env.VITE_DEV_PORT ?? '5174';
  const port = /^\d+$/.test(text) ? Number(text) : 0;
  if (port <= 0 || port >= 65536) throw new Error(`VITE_DEV_PORT must be a TCP port, not ${JSON.stringify(text)}.`);
  return port;
}

/** This run's Vite port. */
export const VITE_PORT = vitePort(process.env);

/** The header with which vite.config.ts says which checkout it serves (`server.headers`, URI-encoded). */
export const VITE_ROOT_HEADER = 'x-erplora-vite-root';

/** What the dev shell loads first from Vite (`live.spa`, LIVE["spa"] in config/settings.py). */
function viteClientUrl(port: number, host = 'localhost'): string {
  return `http://${host}:${port}/static/spa/@vite/client`;
}

/** Vite's hot-update socket on `port` (`server.hmr` of vite.config.ts; its path is `base`, with a token). */
export function viteHmrSocket(port: number): RegExp {
  return new RegExp(`^ws://localhost:${port}/`);
}

/** How to get out of a Vite that is not this checkout's. */
const ANOTHER_PORT = 'Export VITE_DEV_PORT=<a free port> and retry (README.md, «Dos SaaS a la vez»).';

/**
 * Throws unless the Vite on `port` serves `saasDir`. Playwright reuses whatever answers on the port, and
 * a Vite of another checkout (a worker's SaaS of main on 5174) would have the specs test its frontend.
 */
export async function assertViteOfThisTree(saasDir: string, port: number, host = 'localhost'): Promise<void> {
  const url = viteClientUrl(port, host);
  let response: Response;
  try {
    response = await fetch(url);
  } catch (error) {
    throw new Error(`Nothing answers on Vite's port :${port} (GET ${url}: ${String((error as Error).cause ?? error)}).`, {
      cause: error,
    });
  }
  await response.body?.cancel();
  if (!response.ok) {
    throw new Error(`What answers on :${port} is not this checkout's Vite (GET ${url}: ${response.status}). ${ANOTHER_PORT}`);
  }
  const header = response.headers.get(VITE_ROOT_HEADER);
  if (header === null) {
    throw new Error(
      `The Vite on :${port} does not say which checkout it serves (another tree's, older than VITE_DEV_PORT): ` +
        `the panel's specs would test its frontend, not this checkout's (${saasDir}). ${ANOTHER_PORT}`,
    );
  }
  const root = decodeURIComponent(header);
  if (root !== saasDir) {
    throw new Error(
      `The Vite on :${port} serves ${root}, not this checkout (${saasDir}): the panel's specs would test that ` +
        `tree's frontend. ${ANOTHER_PORT}`,
    );
  }
}

export const panelProject: Project = {
  name: 'panel',
  testDir: 'panel',
  // English, whatever the machine's language: the specs read the English texts.
  use: { baseURL: PANEL_URL, locale: 'en-US' },
};

/** Django on :8012 and Vite on `vitePort` (:5174 by default), from saas-next/ (`saasDir`). */
export function panelServers(saasDir: string, vitePort = VITE_PORT): WebServer[] {
  return [
    {
      name: 'panel-django',
      command: 'uv run python manage.py runserver 127.0.0.1:8012 --novite --noreload',
      cwd: saasDir,
      // /healthz answers on any Host and never touches the database (base/health.py).
      url: 'http://127.0.0.1:8012/healthz',
      reuseExistingServer: false,
      timeout: 120_000,
      // Playwright puts its own environment under these, DEBUG included (django-env.ts).
      env: djangoEnv(true, {
        HUB_INTERNAL_URL: `http://127.0.0.1:${HUB_DOUBLE_PORT}`,
        EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
        EMAIL_FILE_PATH: PANEL_MAIL_DIR,
        // Its dev shell and CSP point at this run's Vite.
        VITE_DEV_PORT: String(vitePort),
        // Every spec signs in from 127.0.0.1, past allauth's 30 sign-ins a minute when repeated
        // (config/settings.py): only this server raises that one limit.
        E2E_RELAX_LOGIN_RATE_LIMIT: 'True',
      }),
    },
    {
      name: 'panel-vite',
      command: 'pnpm run dev',
      cwd: saasDir,
      url: viteClientUrl(vitePort),
      // Only this checkout's (globalSetup, `assertViteOfThisTree`).
      reuseExistingServer: true,
      timeout: 60_000,
      env: { VITE_DEV_PORT: String(vitePort) },
    },
  ];
}
