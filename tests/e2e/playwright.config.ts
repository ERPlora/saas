// Browser checks of the public web (`tests/e2e/`): Chrome, headless by default; a visible, slowed-down
// window only when a run asks for it (`E2E_HEADED=1`, `pnpm e2e:headed`), never in CI.
//
// It drives a production-like SaaS of its own: DEBUG off (the public CSP as production serves it,
// no Vite dev server), the build of `pnpm build` (run it first: the manifest must hold
// `frontend/public.ts`), static files served by `runserver --insecure`, on 127.0.0.1:8011 so it never
// collides with the dev server on :8001. `globalSetup` first stops the run if the local database of
// `.env` has unapplied migrations (it never migrates it: sessions share it), then seeds the app the
// specs open and removes it at the end (store_docs_seed.py).
//
// Ports and database are the run's stack's (stack.ts): today's unless E2E_SAAS_PORT moves the ports for a
// second run at once, whose own e2e database a step of its own creates and migrates before any server starts
// (`databaseStep`; Playwright starts the `webServer` entries one after another, and all before globalSetup).
//
// Each run writes its traces and failure screenshots into `.artifacts/test-results/<run id>/`, and the
// specs their evidence into `.artifacts/` (both ignored by git).
//
// Two projects (README.md): `public`, the specs above against that server, and `panel`, the panel's
// specs (`panel/`) against a dev server of its own on :8012 and its twin with the second factor on, :8013
// (panel/project.ts). `pnpm e2e` runs both and
// `--project=public|panel` one, headless; `pnpm e2e:headed` the same in a visible Chrome; `pnpm e2e:ci`
// (CI=1) is the CI run.
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig, type PlaywrightTestConfig } from '@playwright/test';

import { DATABASE_READY } from './database';
import { djangoEnv, productionPolicies } from './django-env';
import { panelProject, panelServers } from './panel/project';
import { recaptchaServerEnv } from './recaptcha';
import { STACK, type Stack } from './stack';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..');
export const BASE_URL = `http://127.0.0.1:${STACK.publicPort}`;

/**
 * Where the public server of `stack` writes the mails it sends (the contact form, PUBLIC-G39), as files: never SMTP.
 * `tests/e2e/.artifacts/public/mail/` (ignored by git), `mail-<E2E_SAAS_PORT>/` beside the shared stack.
 */
export function publicMailDir(stack: Stack): string {
  return join(HERE, '.artifacts', 'public', stack.shared ? 'mail' : `mail-${stack.base}`);
}

/** This run's. */
export const PUBLIC_MAIL_DIR = publicMailDir(STACK);

/**
 * The folder name of a run of `stack` started `now` (`.artifacts/test-results/<id>/`): its start time and, beside
 * the shared stack, its port. Two runs started in the same millisecond shared one, and the first to finish
 * deleted the other's traces.
 */
export function runId(stack: Stack, now: Date): string {
  const started = now.toISOString().replace(/[:.]/g, '-');
  return stack.shared ? started : `${started}-${stack.base}`;
}

process.env.PW_RUN_ID ??= runId(STACK, new Date());

/** Milliseconds between the steps of a visible run, so a person can follow it. */
const SLOW_MO = 150;

/**
 * The browser's window for a run with `env`: headless and at full speed by default;
 * a visible Chrome, slowed down, only with `E2E_HEADED=1`. CI never opens one, whatever it asks.
 */
export function browserWindow(env: Record<string, string | undefined>): { headless: boolean; slowMo: number } {
  const headed = env.E2E_HEADED === '1' && !env.CI;
  return { headless: !headed, slowMo: headed ? SLOW_MO : 0 };
}

const WINDOW = browserWindow(process.env);

type WebServer = Exclude<NonNullable<PlaywrightTestConfig['webServer']>, unknown[]>;

/**
 * How long an own stack's database may take to get ready. It only has to catch a stuck migration: 170 s were measured
 * on a first run with a load of 22, and each migration is its own transaction, so the next run goes on from there.
 */
const DATABASE_STEP_TIMEOUT = 600_000;

/**
 * The step that creates an own stack's database when missing and migrates it (database.ts), so that every server and
 * globalSetup find it ready. An entry of its own and not part of the first server's command, whose two minutes a first
 * migration ran out on a busy machine: Playwright killed it half way and the run ended without a spec. It serves
 * nothing: it is done when it prints its last line. A failed migration ends it with its error, and the run at once.
 */
export function databaseStep(saasDir: string): WebServer {
  return {
    name: 'database',
    command: 'node tests/e2e/database.ts',
    cwd: saasDir,
    wait: { stdout: DATABASE_READY },
    stdout: 'pipe',
    timeout: DATABASE_STEP_TIMEOUT,
  };
}

/** The public server of `stack`, on a database already there: `databaseStep`'s or the shared `saas`. */
export function publicServer(saasDir: string, stack: Stack = STACK, env: Record<string, string | undefined> = process.env): WebServer {
  return {
    command: `uv run python manage.py runserver 127.0.0.1:${stack.publicPort} --novite --insecure --noreload`,
    cwd: saasDir,
    url: `http://127.0.0.1:${stack.publicPort}/robots.txt`,
    reuseExistingServer: false,
    timeout: 120_000,
    // Playwright puts its own environment under these, DEBUG included, and the stack's database (django-env.ts).
    env: djangoEnv(
      false,
      {
        // Production refuses to start without a key; this one only signs this local, throwaway server.
        SECRET_KEY: 'e2e-local-only-not-a-secret',
        // And without its cache prefix and Stripe mode, which ECS gives production explicitly (django-env.ts).
        ...productionPolicies(stack),
        // Production refuses to start without it either (fiscal/): a valid Fernet key that encrypts nothing here.
        FISCAL_DOCUMENTS_KEY: 'ZTJlLWxvY2FsLW9ubHktbm90LWEtc2VjcmV0LWtleSE=',
        ALLOWED_HOSTS: '127.0.0.1,localhost',
        EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
        EMAIL_FILE_PATH: publicMailDir(stack),
        // reCAPTCHA off, as in production; with `E2E_RECAPTCHA=1`, on: its assessments go to the
        // run's double, never to Google, and its pages get a fake enterprise.js (recaptcha.ts).
        ...recaptchaServerEnv(stack, saasDir, env),
        // The run presses «Try the demo» from 127.0.0.1 more than production's 3 an hour (demo-door, public-demo,
        // recaptcha); the throttled door is a spec of its own (`?state=throttled`, public-demo.spec.ts).
        DEMO_SPAWN_RATELIMIT: '30/h',
        // Its Hub is the one demo-wait.spec.ts plays on the stack (nobody listens otherwise: «not available» at once),
        // unless the run walks a real demo (`E2E_DEMO_HUB`, README «La demo contra un Hub de verdad»), whose exported
        // HUB_INTERNAL_URL then reaches the server.
        ...(env.E2E_DEMO_HUB ? {} : { HUB_INTERNAL_URL: `http://127.0.0.1:${stack.publicHubDoublePort}` }),
      },
      stack,
    ),
  };
}

/**
 * The public server's twin with a tracker configured (made-up: nothing loads it until a person accepts), on `stack`'s
 * own port: the only one that shows the cookie notice, as production would the day it measures visits (PUBLIC-F19,
 * step 2). The rest of the specs run with no notice, as production today.
 */
export function publicNoticeServer(saasDir: string, stack: Stack = STACK, env: Record<string, string | undefined> = process.env): WebServer {
  const server = publicServer(saasDir, stack, env);
  return {
    ...server,
    name: 'public-notice',
    command: `uv run python manage.py runserver 127.0.0.1:${stack.publicNoticePort} --novite --insecure --noreload`,
    url: `http://127.0.0.1:${stack.publicNoticePort}/robots.txt`,
    env: { ...server.env, CLARITY_PROJECT_ID: 'e2e-cookie-notice' },
  };
}

/** The double of reCAPTCHA's assessments the public server of `stack` asks (recaptcha-double.ts), never reused. */
export function recaptchaDoubleServer(saasDir: string, stack: Stack = STACK): WebServer {
  return {
    name: 'recaptcha-double',
    command: `node tests/e2e/recaptcha-double.ts ${stack.recaptchaDoublePort}`,
    cwd: saasDir,
    url: `http://127.0.0.1:${stack.recaptchaDoublePort}/healthz`,
    reuseExistingServer: false,
    timeout: 30_000,
  };
}

/** What Playwright starts for a run of `stack`, in this order: the database first, and only on a stack that owns one. */
export function stackServers(saasDir: string, stack: Stack = STACK, env: Record<string, string | undefined> = process.env): WebServer[] {
  return [
    ...(stack.database === undefined ? [] : [databaseStep(saasDir)]),
    recaptchaDoubleServer(saasDir, stack),
    publicServer(saasDir, stack, env),
    publicNoticeServer(saasDir, stack, env),
    ...panelServers(saasDir, undefined, stack, env),
  ];
}

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: join(HERE, '.artifacts', 'test-results', process.env.PW_RUN_ID),
  globalSetup: join(HERE, 'global-setup.ts'),
  // The CI's e2e is part of a required check: a `test.only` left in a spec would turn it green with that one test.
  forbidOnly: Boolean(process.env.CI),
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
  webServer: stackServers(SAAS_DIR),
});
