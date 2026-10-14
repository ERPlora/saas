// What the panel's specs start from: the seeded account (`manage.py demo_seed`), the sign-in
// (allauth.headless's API, or the real /login page when the sign-in is what a spec checks), the
// session /api/me reports, the three viewports, uncaught page errors and the evidence folder.
// Import `test` and `expect` from here, not from `@playwright/test`.
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type APIRequestContext, type Page, test as base, expect } from '@playwright/test';

export { expect };

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..', '..');
const ARTIFACTS = join(HERE, '..', '.artifacts', 'panel');

/** allauth.headless's sign-in for the browser client: what the /login page posts. */
const SIGN_IN_API = '/_allauth/browser/v1/auth/login';

/** A SaaS account: what its sign-in asks for. */
export interface Credentials {
  email: string;
  password: string;
}

/** `demo_seed`'s customer: owner of the local hubs `a` and `b`, no admin and no name of its own. */
export const OWNER: Credentials = { email: 'owner@example.com', password: 'owner' };

/** Phone, tablet and desktop (working rules §2.4). */
export const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
  { width: 1440, height: 900 },
] as const;

/** What `GET /api/me` (`base.session.me`) answers: `user` is null without a session. */
export interface Session {
  user: { id: string; label: string } | null;
  scope: { kind: string; key: string };
}

/**
 * `manage.py demo_seed`, against the database of `.env`: it creates the local accounts that are
 * missing and leaves the rest as they are. It refuses to run without DEBUG, hence `DEBUG=True`.
 */
export function seedAccounts(): void {
  execFileSync('uv', ['run', 'python', 'manage.py', 'demo_seed'], {
    cwd: SAAS_DIR,
    env: { ...process.env, DEBUG: 'True' },
    stdio: 'pipe',
  });
}

/** The session behind `request` (a page's or a context's: they share its cookies). */
export async function sessionOf(request: APIRequestContext): Promise<Session> {
  const response = await request.get('/api/me');
  expect(response.status(), 'GET /api/me').toBe(200);
  return (await response.json()) as Session;
}

/**
 * Signs `request`'s browser context in through allauth.headless, as the /login page does: the SPA's
 * HTML sets Django's CSRF cookie (`live.spa`, `ensure_csrf_cookie`) and the API wants it back in
 * `X-CSRFToken`. The session cookie lands in the context, so its pages are signed in.
 */
export async function signIn(request: APIRequestContext, credentials: Credentials): Promise<void> {
  const login = await request.get('/login');
  expect(login.status(), 'GET /login').toBe(200);
  const { cookies } = await request.storageState();
  const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value;
  if (!csrf) throw new Error('GET /login set no csrftoken cookie');
  const response = await request.post(SIGN_IN_API, { headers: { 'X-CSRFToken': csrf }, data: credentials });
  expect(response.status(), `POST ${SIGN_IN_API}: ${await response.text()}`).toBe(200);
}

/**
 * The real sign-in, on the /login page already open: types `credentials` and submits; the page
 * then leaves for its `next` (or the launcher) with a full load.
 */
export async function signInThroughPage(page: Page, credentials: Credentials): Promise<void> {
  const form = page.getByTestId('login-form');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  await form.getByTestId('login-submit').click();
}

/** Collects the page's uncaught errors from now on (the list fills as they happen). */
export function watchPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  return errors;
}

/** Path of a screenshot under `tests/e2e/.artifacts/panel/` (ignored by git). */
export function shot(name: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  return join(ARTIFACTS, `${name}.png`);
}

/** The accounts of `panel_seed.py` (`e2e-<name>@example.com`), all with the same password. */
export const panelAccount = (name: string): Credentials => ({ email: `e2e-${name}@example.com`, password: 'e2e-panel' });

/**
 * `tests/e2e/panel/panel_seed.py seed|clear`: the businesses panel's accounts and businesses (the
 * launcher's variants, Businesses, a business's page, the invitations), always from scratch.
 */
export function seedPanel(action: 'seed' | 'clear' = 'seed'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/panel_seed.py', action], {
    cwd: SAAS_DIR,
    env: { ...process.env, DEBUG: 'True' },
    stdio: 'pipe',
  });
}

/** The id of the business called `name` among the businesses of `request`'s account. */
export async function businessIdOf(request: APIRequestContext, name: string): Promise<string> {
  const response = await request.get('/api/hubs/businesses?limit=50&offset=0');
  expect(response.status(), 'GET /api/hubs/businesses').toBe(200);
  const rows = ((await response.json()) as { rows: Array<{ id: string; name: string }> }).rows;
  const found = rows.find((row) => row.name === name);
  if (!found) throw new Error(`no business ${name} for this account`);
  return found.id;
}

/** `INTERNAL_SHARED_SECRET` of the local SaaS (`.env`), to sign what the Hub would send. */
export function internalSecret(): string {
  return execFileSync(
    'uv',
    ['run', 'python', '-c', 'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings");django.setup();from django.conf import settings;print(settings.INTERNAL_SHARED_SECRET)'],
    { cwd: SAAS_DIR, env: { ...process.env, DEBUG: 'True' }, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
  ).trim();
}

export const test = base.extend<{ signedInPage: Page }, { owner: Credentials }>({
  // Once per worker: the accounts exist before any spec signs in.
  owner: [
    // Playwright reads a fixture's dependencies from its first parameter's pattern: none here.
    async ({}, use) => {
      seedAccounts();
      await use(OWNER);
    },
    { scope: 'worker' },
  ],
  // A page whose context is signed in as the owner, through the API (fast; no form on screen).
  signedInPage: async ({ page, owner }, use) => {
    await signIn(page.request, owner);
    await use(page);
  },
});
