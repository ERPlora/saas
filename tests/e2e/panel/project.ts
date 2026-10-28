// The panel's project of the e2e (`tests/e2e/panel/`, README.md): the SPA of erplora.com as
// `manage.py runserver` serves it in development, its assets from Vite on :5174 (`VITE_DEV_PORT` moves it,
// for Django and Vite alike). DEBUG on: the SPA's dev shell, and `demo_seed` refuses to run without it.
//
// Its ports, its database and its mail folder are the run's stack's (stack.ts): today's (:8012, the Hub at
// :8019, `.env`'s `saas`, `.artifacts/panel/mail/`) unless E2E_SAAS_PORT moves them, for a second run at once.
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
// Playwright stops what it started at the end, never what it reused. A stack beside the shared one never
// reuses it: a second run of the same checkout on the same port would lose it when the first one ends.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { PlaywrightTestConfig, Project } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { STACK, type Stack } from '../stack';

export const PANEL_URL = `http://localhost:${STACK.panelPort}`;

/**
 * The panel's twin with the second factor on (`ACCOUNTS_MFA_ENABLED`, off by default in phase 1): the same Django on
 * `stack`'s next port, with the same database, Vite, mail folder and Hub double, for the specs of the authenticator
 * app, the trusted browsers and the staff's second factor (accounts/WORKBOOK.md, APP-ACCOUNTS-2). Its pages are
 * `localhost` too: a spec keeps each browser context on one of the two panels, whose cookies would otherwise mix.
 */
export const PANEL_MFA_URL = `http://localhost:${STACK.panelMfaPort}`;

/**
 * Where the panel's Django of `stack` writes the mails it sends (`tests/e2e/.artifacts/panel/mail/`, ignored by
 * git; `mail-<E2E_SAAS_PORT>/` beside the shared stack): two runs reading one folder would take each other's
 * sign-in codes, sent to the same seeded accounts.
 */
export function panelMailDir(stack: Stack): string {
  const panel = join(dirname(fileURLToPath(import.meta.url)), '..', '.artifacts', 'panel');
  return join(panel, stack.shared ? 'mail' : `mail-${stack.base}`);
}

/** This run's. */
export const PANEL_MAIL_DIR = panelMailDir(STACK);

/**
 * The Hub's `/internal` as the panel's Django calls it (`HUB_INTERNAL_URL`). Nobody listens there,
 * so every call fails at once and stays owed, as with the Hub away, except while a spec plays the
 * Hub on it (`startHubDouble`).
 */
export const HUB_DOUBLE_PORT = STACK.hubDoublePort;

/**
 * Meta's app as the panel's Django sees it in the e2e (WHATSAPP-G13, WHATSAPP-G07): made-up ids and secrets, so the
 * specs can sign Meta's webhook as Meta does. Meta itself is never called: nothing here is a real credential.
 */
export const WHATSAPP_E2E = {
  appId: '1234567890',
  appSecret: 'e2e-meta-app-secret',
  verifyToken: 'e2e-meta-verify-token',
  configId: '987654321',
} as const;

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

/** The environment of the panel's Django of `stack` (and of its twin, which adds the second factor on). */
function panelDjangoEnv(vitePort: number, stack: Stack): Record<string, string> {
  // Playwright puts its own environment under these, DEBUG included, and the stack's database (django-env.ts).
  return djangoEnv(
    true,
    {
      HUB_INTERNAL_URL: `http://127.0.0.1:${stack.hubDoublePort}`,
      EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
      EMAIL_FILE_PATH: panelMailDir(stack),
      // Its dev shell and CSP point at this run's Vite.
      VITE_DEV_PORT: String(vitePort),
      // Every spec signs in from 127.0.0.1, password and code, and signs its accounts up from there, past the
      // limits per address when repeated (config/settings.py): only this server raises them (sign-ins, failed
      // passwords, typed codes, sign-ups).
      E2E_RELAX_LOGIN_RATE_LIMIT: 'True',
      // reCAPTCHA off, whatever `.env` holds: the specs sign in through allauth's API, with no browser to ask
      // Google for a token. The public server checks it (recaptcha.spec.ts, recaptcha.ts).
      RECAPTCHA_ENABLED: 'False',
      // Meta's app of the WhatsApp specs (WHATSAPP_E2E): its webhook answers instead of 503.
      WHATSAPP_APP_ID: WHATSAPP_E2E.appId,
      WHATSAPP_APP_SECRET: WHATSAPP_E2E.appSecret,
      WHATSAPP_VERIFY_TOKEN: WHATSAPP_E2E.verifyToken,
      WHATSAPP_CONFIG_ID: WHATSAPP_E2E.configId,
      // The assistant's embeddings and voice go to the e2e's own provider (assistant_seed.py, the local fake on
      // `aiProviderPort`), never to a provider «openai» the shared database may hold with a real key.
      ASSISTANT_SERVICE_PROVIDER: 'e2e-local',
    },
    stack,
  );
}

/** A Django of the panel on `port`, never reused (another session's would reload under the specs). */
function panelDjango(name: string, saasDir: string, port: number, env: Record<string, string>): WebServer {
  return {
    name,
    command: `uv run python manage.py runserver 127.0.0.1:${port} --novite --noreload`,
    cwd: saasDir,
    // /healthz answers on any Host and never touches the database (base/health.py).
    url: `http://127.0.0.1:${port}/healthz`,
    reuseExistingServer: false,
    timeout: 120_000,
    env,
  };
}

/**
 * Django on `stack`'s panel port (:8012 by default), its twin with the second factor on (:8013) and Vite on
 * `vitePort` (:5174 by default), from saas/ (`saasDir`).
 */
export function panelServers(saasDir: string, vitePort = VITE_PORT, stack: Stack = STACK): WebServer[] {
  const env = panelDjangoEnv(vitePort, stack);
  return [
    panelDjango('panel-django', saasDir, stack.panelPort, env),
    panelDjango('panel-mfa-django', saasDir, stack.panelMfaPort, { ...env, ACCOUNTS_MFA_ENABLED: 'True' }),
    {
      name: 'panel-vite',
      command: 'pnpm run dev',
      cwd: saasDir,
      url: viteClientUrl(vitePort),
      // Only this checkout's (globalSetup, `assertViteOfThisTree`), and only on the shared stack.
      reuseExistingServer: stack.shared,
      timeout: 60_000,
      env: { VITE_DEV_PORT: String(vitePort) },
    },
  ];
}
