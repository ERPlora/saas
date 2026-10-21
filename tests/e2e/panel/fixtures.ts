// What the panel's specs start from: the seeded account (`manage.py demo_seed`), the sign-in
// (allauth.headless's API, or the real form of the launcher when the sign-in is what a spec checks), both
// with the code every password sign-in mails (read from the panel's mail folder, as the person reads it),
// the session /api/me reports, the three viewports, uncaught page errors and the evidence folder.
// Import `test` and `expect` from here, not from `@playwright/test`.
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { readMailCode, readPasswordResetLink, waitForMail as waitForMailIn } from '@erplora/ui/testing/mail';
import { type APIRequestContext, type APIResponse, type BrowserContext, type Page, test as base, expect } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { HUB_DOUBLE_PORT, PANEL_MAIL_DIR, VITE_PORT, viteHmrSocket } from './project';

export { expect };

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..', '..');
const ARTIFACTS = join(HERE, '..', '.artifacts', 'panel');

/** allauth.headless's sign-in for the browser client: what the launcher's form posts. */
const SIGN_IN_API = '/_allauth/browser/v1/auth/login';
/** The second step of every password sign-in: the code mailed to the account (what /verify-email posts). */
const CONFIRM_CODE_API = '/_allauth/browser/v1/auth/code/confirm';

/** A SaaS account: what its sign-in asks for. */
export interface Credentials {
  email: string;
  password: string;
}

/**
 * `demo_seed`'s customer: owner of the local hubs `a` and `b`, no admin and no name of its own. The QA users of
 * the root `.env` (`QA_OWNER_*`) name it, with these as their defaults (playwright.config.ts loads them).
 */
export const OWNER: Credentials = {
  email: process.env.QA_OWNER_EMAIL ?? 'owner@example.com',
  password: process.env.QA_OWNER_PASSWORD ?? 'owner',
};

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
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

/** The session behind `request` (a page's or a context's: they share its cookies). */
export async function sessionOf(request: APIRequestContext): Promise<Session> {
  const response = await request.get('/api/me');
  expect(response.status(), 'GET /api/me').toBe(200);
  return (await response.json()) as Session;
}

/** The CSRF token of `request`'s cookies (the SPA's HTML sets it; a sign-in rotates it). */
async function csrfOf(request: APIRequestContext): Promise<string> {
  const { cookies } = await request.storageState();
  const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value;
  if (!csrf) throw new Error('no csrftoken cookie: load a page of the SPA first');
  return csrf;
}

/**
 * Signs `request`'s browser context in through allauth.headless, as the launcher's form and /verify-email
 * do: the SPA's HTML sets Django's CSRF cookie (`live.spa`, `ensure_csrf_cookie`) and the API wants it back
 * in `X-CSRFToken`; the password waits for the code mailed to the account (`login_by_code`), read from the
 * panel's mail folder (the newest to that address since the password was posted) and confirmed. The session
 * cookie lands in the context, so its pages are signed in.
 */
export async function signIn(request: APIRequestContext, credentials: Credentials): Promise<void> {
  const launcher = await request.get('/launch');
  expect(launcher.status(), 'GET /launch').toBe(200);
  const csrf = await csrfOf(request);
  const since = Date.now();
  const password = await request.post(SIGN_IN_API, { headers: { 'X-CSRFToken': csrf }, data: credentials });
  const waiting = (await password.json()) as { data?: { flows?: Array<{ id: string; is_pending?: boolean }> } };
  const pending = waiting.data?.flows?.filter((flow) => flow.is_pending).map((flow) => flow.id);
  expect([password.status(), pending], `POST ${SIGN_IN_API}: ${JSON.stringify(waiting)}`).toEqual([401, ['login_by_code']]);
  const code = await waitForMailCode(credentials.email, since);
  const confirmed = await request.post(CONFIRM_CODE_API, { headers: { 'X-CSRFToken': csrf }, data: { code } });
  expect(confirmed.status(), `POST ${CONFIRM_CODE_API}: ${await confirmed.text()}`).toBe(200);
}

/**
 * The launcher's form, already on screen: types `credentials` and submits. The page then goes to
 * /verify-email for the mailed code (or leaves, signed in, when no code is asked).
 */
export async function submitSignInForm(page: Page, credentials: Credentials): Promise<void> {
  const form = page.getByTestId('login-form');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  await form.getByTestId('login-submit').click();
}

/**
 * The real sign-in, on the launcher's form already on screen: the password, then the code mailed to the
 * account, typed on /verify-email as the person does. The page then leaves for its `next` (or the
 * launcher) with a full load.
 */
export async function signInThroughPage(page: Page, credentials: Credentials): Promise<void> {
  const since = Date.now();
  await submitSignInForm(page, credentials);
  await expect(page).toHaveURL(/\/verify-email(\?|$)/);
  const code = await waitForMailCode(credentials.email, since);
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).not.toHaveURL(/\/verify-email(\?|$)/);
}

/** This run's Vite's hot-update socket (`VITE_DEV_PORT`, panel/project.ts). */
const VITE_HMR = viteHmrSocket(VITE_PORT);

/**
 * Cuts `context`'s pages off from Vite's hot updates: the socket opens, answered by the spec, and
 * nothing arrives. Another session saving a `.vue` mid-run (a shared component, DataTable) would
 * otherwise remount components under the spec and leave an open dialog behind. Every page load
 * still gets the files as they are on disk. The `context` of every panel spec already has it.
 */
export async function freezeFrontend(context: BrowserContext): Promise<void> {
  await context.routeWebSocket(VITE_HMR, () => {});
}

/**
 * What scrolls sideways on the page on screen: Ionic pins `body` (its width never grows), so the
 * scroll is read where it happens — the page's `ion-content` scroll box (in its shadow) and every
 * DataTable's own scroll box, which also says so with `data-table__scroll--overflow`.
 */
export async function sidewaysScroll(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const found: string[] = [];
    const content = shown.querySelector('ion-content');
    const scroll = content?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');
    if (scroll && scroll.scrollWidth > scroll.clientWidth + 1) found.push(`ion-content ${scroll.scrollWidth} > ${scroll.clientWidth}`);
    for (const table of shown.querySelectorAll<HTMLElement>('.data-table__scroll')) {
      if (table.scrollWidth > table.clientWidth + 1) found.push(`data-table ${table.scrollWidth} > ${table.clientWidth}`);
      if (table.classList.contains('data-table__scroll--overflow')) found.push('data-table__scroll--overflow');
    }
    return found;
  });
}

/**
 * Settled: the fonts loaded, no transition of Ionic running (endless spinners aside) and the page painted as it
 * is now. The last one is what a screenshot right after `setViewportSize` needs: taken before the browser paints
 * a frame at the new size, it repeats the top of the page at its bottom (`repeatedTop`).
 */
export async function settled(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every((animation) => animation.playState !== 'running' || animation.effect?.getTiming().iterations === Infinity),
  );
  // A frame's callbacks run before it is painted; the next frame's, once it has been.
  await page.evaluate(() => new Promise<void>((painted) => requestAnimationFrame(() => requestAnimationFrame(() => painted()))));
}

/** The fewest rows `repeatedTop` counts as a stripe. */
const STRIPE_MIN_ROWS = 8;

/**
 * How many rows at the bottom of `png`, a screenshot of `page`, repeat the first rows of the image: 0 when
 * none. It is what a capture taken before the browser painted the page at its new size shows (the area the
 * resize uncovered, filled with the top of the page): evidence of a screen nobody saw. A stripe of one flat
 * colour (a background at both ends) does not count. Decoded in `page`'s browser: the e2e has no image library.
 */
export async function repeatedTop(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(
    async ({ base64, minRows }) => {
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const { width, height } = bitmap;
      const context = new OffscreenCanvas(width, height).getContext('2d');
      if (!context) throw new Error('repeatedTop: no 2d context to read the screenshot');
      context.drawImage(bitmap, 0, 0);
      const pixels = new Uint32Array(context.getImageData(0, 0, width, height).data.buffer);
      const sameRow = (a: number, b: number) => {
        for (let x = 0; x < width; x++) if (pixels[a * width + x] !== pixels[b * width + x]) return false;
        return true;
      };
      const flatRow = (row: number) => {
        for (let x = 1; x < width; x++) if (pixels[row * width + x] !== pixels[row * width]) return false;
        return true;
      };
      for (let rows = Math.floor(height / 2); rows >= minRows; rows--) {
        let repeated = true;
        let flat = true;
        for (let row = 0; row < rows && repeated; row++) {
          repeated = sameRow(height - rows + row, row);
          flat &&= flatRow(row);
        }
        if (repeated && !flat) return rows;
      }
      return 0;
    },
    { base64: png.toString('base64'), minRows: STRIPE_MIN_ROWS },
  );
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

/**
 * The accounts of `panel_seed.py` (`e2e-<name>@example.com`), all with the same password: `QA_PANEL_PASSWORD`
 * of the root `.env` (playwright.config.ts loads it), the seed's own default otherwise.
 */
export const panelAccount = (name: string): Credentials => ({
  email: `e2e-${name}@example.com`,
  password: process.env.QA_PANEL_PASSWORD ?? 'e2e-panel',
});

/**
 * A QA user of the root `.env` (`QA_<ROLE>_EMAIL`, `QA_<ROLE>_PASSWORD`, README «Usuarios QA») when exported,
 * else `fallback`: the same values its seed falls back to (`billing_seed.py`, `store_seed.py`).
 */
export const qaAccount = (role: string, fallback: Credentials): Credentials => ({
  email: process.env[`QA_${role}_EMAIL`] ?? fallback.email,
  password: process.env[`QA_${role}_PASSWORD`] ?? fallback.password,
});

/**
 * `tests/e2e/panel/panel_seed.py seed|clear`: the businesses panel's accounts and businesses (the
 * launcher's variants, Businesses, a business's page, the invitations), always from scratch.
 */
export function seedPanel(action: 'seed' | 'clear' = 'seed'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/panel_seed.py', action], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
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

/**
 * What `code` prints, run with Django set up against the run's database (DEBUG on): the local one of `.env`,
 * or the stack's own (stack.ts). For what a spec reads from the SaaS's side and no page shows.
 */
export function djangoPrint(code: string): string {
  const boot = 'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings");django.setup()';
  return execFileSync('uv', ['run', 'python', '-c', `${boot}\n${code}`], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    encoding: 'utf8',
    // stderr kept, not shown: uv's warnings; a failing snippet's traceback travels in the thrown error.
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

/** `INTERNAL_SHARED_SECRET` of the local SaaS (`.env`), to sign what the Hub would send. */
export function internalSecret(): string {
  return djangoPrint('from django.conf import settings;print(settings.INTERNAL_SHARED_SECRET)');
}

/**
 * A POST to the panel's API as `request`'s account, with Django's CSRF token from its cookies (set
 * by the SPA's HTML, so after `signIn` or a page load).
 */
export async function apiPost(request: APIRequestContext, path: string, data: unknown): Promise<APIResponse> {
  const { cookies } = await request.storageState();
  const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value;
  if (!csrf) throw new Error(`POST ${path}: no csrftoken cookie (sign in first)`);
  return request.post(path, { headers: { 'X-CSRFToken': csrf }, data });
}

// ── The mails the panel's Django sends (file backend, project.ts) ─────────────────────────────
// Read with `@erplora/ui/testing/mail`, shared with the Hub's e2e: the newest matching mail to the address
// written from `since` on (a `Date.now()` taken before the action that sends it), so an earlier run's or an
// earlier test's code to the same address is never read.

/** The first group (or the whole match) of `match` in the newest mail to `to` since `since`. */
export async function waitForMail(to: string, since: number, match: RegExp): Promise<string> {
  return waitForMailIn({ dir: PANEL_MAIL_DIR, to, since, match });
}

/**
 * The six digits mailed to `to` from `since` on: the sign-in code of every password sign-in
 * (`ACCOUNT_LOGIN_BY_CODE_FORMAT`) or the one that proves the address of a sign-up
 * (`ACCOUNT_EMAIL_VERIFICATION_BY_CODE_FORMAT`), alone on their line.
 */
export async function waitForMailCode(to: string, since: number): Promise<string> {
  return readMailCode({ dir: PANEL_MAIL_DIR, to, since });
}

/**
 * The password reset link mailed `to` from `since` on: the SPA's `/password/reset/key/<key>` on the panel
 * the request came to (`HEADLESS_FRONTEND_URLS`), as the person clicks it.
 */
export async function waitForPasswordResetLink(to: string, since: number): Promise<string> {
  return readPasswordResetLink({ dir: PANEL_MAIL_DIR, to, since });
}

// ── The Hub, played by a spec ─────────────────────────────────────────────────────────────────

/** A call the SaaS made to the Hub's `/internal`, as the double received it. */
export interface HubCall {
  method: string;
  path: string;
  body: Record<string, unknown>;
  /** Carries the timestamp and the signature every internal call is sent with. */
  signed: boolean;
}

export interface HubDouble {
  calls: HubCall[];
  close(): Promise<void>;
}

/** What the double acknowledges as the Hub does; any other call finds the Hub away (503, stays owed). */
const PLAYED = [
  /^PUT \/internal\/hubs\/[0-9a-f-]+\/state$/,
  /^POST \/internal\/sessions\/revoke$/,
  // WhatsApp's doors 1 and 2 (whatsapp.spec.ts): a message or a status erplora.com hands the Hub.
  /^POST \/internal\/whatsapp\/(inbound|status)$/,
];

/**
 * Plays the Hub on `HUB_DOUBLE_PORT`, where the panel's Django sends its calls (project.ts), until
 * `close()`: it records every call and acknowledges the snapshot push, the session revocation and WhatsApp's doors.
 * Outside it nobody listens there and every call stays owed, as with the Hub away.
 */
export async function startHubDouble(): Promise<HubDouble> {
  const calls: HubCall[] = [];
  const server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on('data', (chunk: Buffer) => chunks.push(chunk));
    request.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      const method = request.method ?? '';
      const path = request.url ?? '';
      calls.push({
        method,
        path,
        body: raw ? (JSON.parse(raw) as Record<string, unknown>) : {},
        signed: !!request.headers['x-erplora-timestamp'] && !!request.headers['x-erplora-signature'],
      });
      const played = PLAYED.some((route) => route.test(`${method} ${path}`));
      response.writeHead(played ? 200 : 503, { 'Content-Type': 'application/json' });
      response.end(played ? '{}' : '{"error":{"code":"hub_away"}}');
    });
  });
  await new Promise<void>((listening, failed) => {
    server.once('error', failed);
    server.listen(HUB_DOUBLE_PORT, '127.0.0.1', () => listening());
  });
  return {
    calls,
    close: () =>
      new Promise<void>((closed) => {
        server.closeAllConnections();
        server.close(() => closed());
      }),
  };
}

export const test = base.extend<{ signedInPage: Page }, { owner: Credentials }>({
  // Every page of a spec: no hot updates mid-spec (`freezeFrontend`).
  context: async ({ context }, use) => {
    await freezeFrontend(context);
    await use(context);
  },
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
