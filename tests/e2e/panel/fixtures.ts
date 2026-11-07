// What the panel's specs start from: the seeded account (`manage.py demo_seed`), the sign-in
// (allauth.headless's API, or the real form of the launcher when the sign-in is what a spec checks), both
// with the code every password sign-in mails (read from the panel's mail folder, as the person reads it),
// the session /api/me reports, the three viewports (and a spec's walk through them, with its captures), a spec's
// seed (with its sign-in), a dialog in place after a resize, uncaught page errors, the evidence folder, and Stripe
// played at the page (its Stripe.js and the answer of `billing.checkout.start`).
// Import `test` and `expect` from here, not from `@playwright/test`.
import { execFile, execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { mkdirSync, readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import { readMailCode, readPasswordResetLink, waitForMail as waitForMailIn } from '@erplora/ui/testing/mail';
import {
  type APIRequestContext,
  type APIResponse,
  type BrowserContext,
  type Locator,
  type Page,
  test as base,
  expect,
} from '@playwright/test';

import { djangoEnv } from '../django-env';
import { startWarm, type WarmDjango } from '../django-warm';
import { overflowingBoxes } from '../horizontal-overflow';
import { HUB_DOUBLE_PORT, PANEL_MAIL_DIR, VITE_PORT, viteHmrSocket } from './project';

export { expect };

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = resolve(HERE, '..', '..', '..');
const ARTIFACTS = join(HERE, '..', '.artifacts', 'panel');

/** allauth.headless's sign-in for the browser client: what the launcher's form posts. */
const SIGN_IN_API = '/_allauth/browser/v1/auth/login';
/** The second step of every password sign-in: the code mailed to the account (what /verify-email posts). */
export const CONFIRM_CODE_API = '/_allauth/browser/v1/auth/code/confirm';

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
 * Signs the page's context in as `credentials`, signing out whoever was in (allauth refuses a second sign-in: 409).
 * The page leaves first: left open, it sees its session end, reloads and asks for it again, and an answer that comes
 * after the code to a request that carried the password step's cookie deletes the new session's
 * (panel/sign-in-as.spec.ts).
 */
export async function signInAs(page: Page, credentials: Credentials): Promise<void> {
  await page.goto('about:blank');
  await page.context().clearCookies();
  await signIn(page.request, credentials);
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
 * scroll is read where it happens — the scroll box of every `ion-content` and the document (a page
 * that is no Ionic page, Django's admin or a template, scrolls its document: ACCOUNTS-G09), by the one
 * measure (`overflowingBoxes` of ../horizontal-overflow.ts, past 1 px), and every DataTable's own
 * scroll box of the page, which also says so with `data-table__scroll--overflow`.
 */
export async function sidewaysScroll(page: Page): Promise<string[]> {
  const boxes = await overflowingBoxes(page, 1);
  const tables = await page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const found: string[] = [];
    for (const table of shown.querySelectorAll<HTMLElement>('.data-table__scroll')) {
      if (table.scrollWidth > table.clientWidth + 1) found.push(`data-table ${table.scrollWidth} > ${table.clientWidth}`);
      if (table.classList.contains('data-table__scroll--overflow')) found.push('data-table__scroll--overflow');
    }
    return found;
  });
  return [...boxes, ...tables];
}

/**
 * Nothing scrolls sideways (`sidewaysScroll`) once the page has re-laid out, `label` naming the failure. Right after a
 * resize, or the assistant docking beside the page, a DataTable fits its new box over a few frames (folds its row
 * actions, then hands over to cards): one measure taken at once can catch the list half-way, still as wide as before,
 * and report a scroll nobody sees (saas#319). On the real Hub of a cross spec, its side menu (`ion-split-pane`) stays
 * pinned for a frame after the window shrinks below `lg`, its page 150 px wide (saas#380). So it is measured until it
 * has settled.
 */
export async function expectNoSidewaysScroll(page: Page, label: string): Promise<void> {
  await expect.poll(() => sidewaysScroll(page), { message: label }).toEqual([]);
}

/** How long `settled` waits for the page to stop moving: Ionic's overlays enter in well under a second. */
const SETTLE_TIMEOUT_MS = 10_000;

/**
 * What moves on the page now (run in the page, so self-contained): every finite animation running in the document
 * and in every open shadow root under it, however deep. `document.getAnimations()` leaves shadow roots out, and
 * Ionic animates its overlays (`ion-toast`, `ion-modal`, `ion-popover`) inside theirs. Endless ones (spinners)
 * never stop, so they never count.
 */
function movingInPage(): string[] {
  const roots: Array<Document | ShadowRoot> = [document];
  const moving: string[] = [];
  for (const root of roots) {
    for (const element of root.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
    for (const animation of root.getAnimations()) {
      if (animation.playState !== 'running' || animation.effect?.getTiming().iterations === Infinity) continue;
      const target = (animation.effect as KeyframeEffect | null)?.target;
      moving.push(`${root instanceof ShadowRoot ? `${root.host.localName} › ` : ''}${target?.localName ?? '?'}`);
    }
  }
  return moving;
}

/** A page that navigates while `settled` asks what moves: it asks the new page next (as `waitForFunction` did). */
function navigating(error: Error): string[] {
  if (!/Execution context was destroyed/.test(error.message)) throw error;
  return ['(navigating)'];
}

/**
 * Settled: the fonts loaded, nothing moving (an overlay of Ionic entering included; endless spinners aside) and the
 * page painted as it is now. The last one is what a screenshot right after `setViewportSize` needs: taken before the
 * browser paints a frame at the new size, it repeats the top of the page at its bottom (`repeatedTop`). A page that
 * still moves after `SETTLE_TIMEOUT_MS` fails the spec, naming what moves.
 */
export async function settled(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await expect
    .poll(() => page.evaluate(movingInPage).catch(navigating), { message: 'settled(): still moving', timeout: SETTLE_TIMEOUT_MS, intervals: [16] })
    .toEqual([]);
  // A frame's callbacks run before it is painted; the next frame's, once it has been.
  await page.evaluate(() => new Promise<void>((painted) => requestAnimationFrame(() => requestAnimationFrame(() => painted()))));
}

/** The panel's side menu: pinned from `lg` (992 px), its drawer behind the topbar's menu button below. Opens the drawer
 *  when the menu is not on screen, and waits until it has slid in with its entries inside the screen. */
export async function openMenu(page: Page): Promise<void> {
  const entries = page.locator('ion-menu .nav-item');
  await expect(entries.first()).toBeAttached();
  await settled(page);
  if (!(await entries.first().isVisible())) {
    await page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button').last().click();
    await expect(entries.first()).toBeVisible();
    // The drawer slides in: it counts as open once its animation ends and its entries sit inside the screen.
    await expect
      .poll(() => page.evaluate(() => (document.querySelector('ion-menu') as (HTMLElement & { isOpen: () => Promise<boolean> }) | null)?.isOpen() ?? false))
      .toBe(true);
    await expect.poll(async () => (await entries.first().boundingBox())?.x ?? -1).toBeGreaterThanOrEqual(0);
  }
}

/** Closes the drawer `openMenu` opened (nothing to do where the menu is pinned). */
export async function closeMenu(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const menu = document.querySelector('ion-menu') as (HTMLElement & { close?: () => Promise<boolean> }) | null;
    await menu?.close?.();
  });
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

/**
 * The `/api/live` streams a page opens (the operations of each, from `s=`) and the ones that failed. A page declares
 * its live data when it mounts, so its stream opens once; a subscription arriving after the first open makes the SDK
 * reopen it, and the first request ends `ERR_ABORTED` (FIX-SAAS-BUSINESSES-LIVE-DOUBLE-OPEN).
 */
export function watchLiveStreams(page: Page): { opened: string[][]; failed: string[] } {
  const opened: string[][] = [];
  const failed: string[] = [];
  const isStream = (url: string) => new URL(url).pathname === '/api/live';
  page.on('request', (request) => {
    if (!isStream(request.url())) return;
    const s = new URL(request.url()).searchParams.get('s') ?? '';
    const list = JSON.parse(Buffer.from(s, 'base64url').toString('utf8')) as { op: string; params: unknown }[];
    opened.push(list.map((sub) => `${sub.op} ${JSON.stringify(sub.params)}`));
  });
  page.on('requestfailed', (request) => {
    if (isStream(request.url())) failed.push(request.failure()?.errorText ?? 'failed');
  });
  return { opened, failed };
}

/** Longer than the SDK's resubscribe debounce (150 ms) and a round trip: a late subscription would reopen by then. */
export const QUIET_MS = 1500;

/** Path of a screenshot under `tests/e2e/.artifacts/panel/` (ignored by git). */
export function shot(name: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  return join(ARTIFACTS, `${name}.png`);
}

/** One of `VIEWPORTS`. */
export type Viewport = (typeof VIEWPORTS)[number];

/** What a spec's walk through `VIEWPORTS` (`captureAtEverySize`) adds at each size. */
export interface EverySizeOptions {
  /** The whole page captured (the default), or what the window shows. */
  fullPage?: boolean;
  /** What is captured instead of the page: a card whose page scrolls inside its content. */
  of?: Locator;
  /** What follows the width in the capture's name, `<prefix>-<key>-<width>-<suffix>`: the language of the run. */
  suffix?: string;
  /** The spec's own checks once nothing scrolls sideways, before the capture. */
  checks?: (size: Viewport) => Promise<void>;
  /** What undoes `ready` once the capture is taken, before the next size: the menu it opened, closed. */
  after?: () => Promise<void>;
}

/**
 * A spec's walk through `VIEWPORTS` (`captureAtEverySize`): `ready` at each size, then the capture. `options` may be
 * `fullPage` alone, as the billing specs pass it (`false`: what the window shows).
 */
export type AtEverySize = (
  page: Page,
  key: string,
  ready: (size: Viewport) => Promise<void>,
  options?: boolean | EverySizeOptions,
) => Promise<void>;

/**
 * The walk through `VIEWPORTS` of the specs whose captures start with `prefix`: at each size, `ready`; once the page
 * has settled nothing scrolls sideways (`<key> at <width>`), the spec's `checks` pass, and a capture
 * `<prefix>-<key>-<width>` (or `…-<width>-<suffix>`) is taken, of the whole page or of `of`; then `after`. It ends
 * back at the desktop size.
 */
export function captureAtEverySize(prefix: string): AtEverySize {
  return async (page, key, ready, options = {}) => {
    const { fullPage = true, of, suffix, checks, after }: EverySizeOptions =
      typeof options === 'boolean' ? { fullPage: options } : options;
    for (const size of VIEWPORTS) {
      await page.setViewportSize(size);
      await ready(size);
      await settled(page);
      expect(await sidewaysScroll(page), `${key} at ${size.width}`).toEqual([]);
      await checks?.(size);
      const path = shot(suffix === undefined ? `${prefix}-${key}-${size.width}` : `${prefix}-${key}-${size.width}-${suffix}`);
      await (of ? of.screenshot({ path }) : page.screenshot({ path, fullPage }));
      await after?.();
    }
    await page.setViewportSize(VIEWPORTS[VIEWPORTS.length - 1]);
  };
}

/**
 * A dialog that slides in again at a new size (below 640px it is a sheet from the bottom) is in place once its
 * button `testid` is whole on screen and stays put for a frame: the slide runs in Ionic's shadow DOM, where
 * `settled` does not see it, and a capture taken before shows the sheet halfway.
 */
export async function dialogInPlace(page: Page, testid: string): Promise<void> {
  const button = page.getByTestId(testid);
  await expect(button).toBeInViewport({ ratio: 1 });
  await button.evaluate(
    (element) =>
      new Promise<void>((still) => {
        let last = '';
        const frame = () => {
          const { top, left, width, height } = element.getBoundingClientRect();
          const now = `${top},${left},${width},${height}`;
          if (now === last) still();
          else {
            last = now;
            requestAnimationFrame(frame);
          }
        };
        requestAnimationFrame(frame);
      }),
  );
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

/** What a Django process needs for what it mails to land in the panel's mail folder, as the panel's server does. */
export const MAILING: Readonly<Record<string, string>> = {
  EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
  EMAIL_FILE_PATH: PANEL_MAIL_DIR,
};

/** The logo of the branded mails, and the SaaS's file it is. */
export const MAIL_LOGO_URL = 'https://erplora.com/static/public/img/logo.png';
const MAIL_LOGO_FILE = resolve(SAAS_DIR, 'public', 'static', 'public', 'img', 'logo.png');

/**
 * From here on `page` fetches nothing but the mails' logo, served from its file, and writes down every address it
 * asks for (the list returned): a mail painted with `setContent` asks for the logo and nothing else.
 */
export async function onlyTheMailLogo(page: Page): Promise<string[]> {
  const fetched: string[] = [];
  await page.route('**/*', (route) => {
    fetched.push(route.request().url());
    return route.abort();
  });
  await page.route(MAIL_LOGO_URL, (route) => {
    fetched.push(route.request().url());
    return route.fulfill({ path: MAIL_LOGO_FILE, contentType: 'image/png' });
  });
  return fetched;
}

/**
 * `tests/e2e/panel/<script> <args…>` (`panel_seed.py seed|clear`, `assistant_seed.py <action> <provider address>`,
 * `whatsapp_hub_seed.py <a> <b> --used N`…), against the run's database (DEBUG on) with `env` over it (`MAILING`,
 * another stack's database): the last line it printed, where the seeds that tell what they made print it.
 */
export function runSeed(script: string, args: string | readonly string[], env: Readonly<Record<string, string>> = {}): string {
  const out = execFileSync('uv', ['run', 'python', `tests/e2e/panel/${script}`, ...[args].flat()], {
    cwd: SAAS_DIR,
    env: { ...djangoEnv(true), ...env },
    encoding: 'utf8',
    stdio: 'pipe',
  });
  return out.trim().split('\n').at(-1) ?? '';
}

/**
 * `tests/e2e/panel/panel_seed.py seed|clear`: the businesses panel's accounts and businesses (the
 * launcher's variants, Businesses, a business's page, the invitations), always from scratch.
 */
export function seedPanel(action: 'seed' | 'clear' = 'seed'): void {
  runSeed('panel_seed.py', action);
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

const DJANGO_BOOT = 'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings");django.setup()';

/**
 * What `code` prints, run with Django set up against the run's database (DEBUG on): the local one of `.env`,
 * or the stack's own (stack.ts). For what a spec reads from the SaaS's side and no page shows.
 *
 * It blocks this process until `code` ends, and the Hub a spec plays (`startHubDouble`) lives in this process: code
 * that calls that Hub runs with `djangoPrintAsync`, or every call waits out its timeout unanswered (saas#176).
 * Each call boots Django cold: about 1 s on an idle machine, 57 s and 88 s on a loaded one, and the test's timeout
 * cannot fire until it returns (saas#346). Inside a test, read what the panel shows through its API, and what only
 * Django knows once for the spec, in a hook.
 */
export function djangoPrint(code: string): string {
  return execFileSync('uv', ['run', 'python', '-c', `${DJANGO_BOOT}\n${code}`], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    encoding: 'utf8',
    // stderr kept, not shown: uv's warnings; a failing snippet's traceback travels in the thrown error.
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

/** A fresh account of a spec, its address proven, speaking `language` (the account's language wins on the panel). */
export function provenAccount(email: string, password: string, language: 'en' | 'es' = 'en'): void {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email=${JSON.stringify(email)}, password=${JSON.stringify(password)}, language="${language}")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
}

/**
 * The text of `key` (`hubs.domain.title`) in the panel catalogue of `app` (`<app>/frontend/locale/<language>.json`), its
 * `{placeholders}` filled; of a plural (`one | other`), the form for `count`. A spec reads a screen's words from there.
 */
export function catalogueText(app: string, language: 'en' | 'es', key: string, params: Record<string, string | number> = {}): string {
  const catalogue = JSON.parse(readFileSync(join(SAAS_DIR, app, 'frontend', 'locale', `${language}.json`), 'utf8')) as unknown;
  const text = key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalogue);
  if (typeof text !== 'string') throw new Error(`no text ${key} in ${app}/frontend/locale/${language}.json`);
  const forms = text.split(' | ');
  const form = forms.length > 1 && params.count !== 1 ? forms[1] : forms[0];
  return form.replace(/\{(\w+)\}/g, (_, name: string) => String(params[name] ?? `{${name}}`));
}

/**
 * A business of `request`'s account called `name` (created through the API, as the panel creates it), ready as the Hub's
 * callback leaves it and with nothing owed to the Hub, on the plan `plan` (its slug); its id. For inside a test: the
 * rest of what the Hub's callback leaves goes through this worker's warm Django (`djangoPrintWarm`, saas#354).
 */
export async function readyBusinessOn(request: APIRequestContext, name: string, plan: string): Promise<string> {
  const created = await apiPost(request, '/api/hubs/businesses', { name, country: 'ES' });
  expect(created.status(), await created.text()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  await djangoPrintWarm(
    [
      'from django.utils import timezone',
      'from hubs.models import Hub, Plan, Subscription',
      `Hub.objects.filter(pk=${JSON.stringify(id)}).update(status="active", ready_at=timezone.now(), pending_hub_call="")`,
      `Subscription.objects.filter(hub_id=${JSON.stringify(id)}).update(plan=Plan.objects.get(slug=${JSON.stringify(plan)}))`,
    ].join('\n'),
  );
  return id;
}

/**
 * The snippet that removes what a spec leaves behind: the businesses and the accounts whose email starts with `prefix`,
 * and the billing profiles they would leave ownerless (as panel_seed.py's `clear`): the accounts' own (`owner` is
 * SET_NULL) and the ownerless ones of the businesses, after the businesses (their PROTECT). Another account's profile
 * stays, even one that paid a business a spec's account worked in. A profile of theirs still there fails the snippet.
 * Its own tests: config/tests/test_e2e_removing_accounts.py.
 */
const removingAccountsOf = (prefix: string) =>
  [
    'from django.contrib.auth import get_user_model',
    'from hubs.models import BillingProfile, Hub',
    `users = get_user_model().objects.filter(email__startswith=${JSON.stringify(prefix)})`,
    `hubs = Hub.objects.filter(members__user__email__startswith=${JSON.stringify(prefix)})`,
    'profiles = {*hubs.filter(billing_profile__owner=None).values_list("billing_profile_id", flat=True), *BillingProfile.objects.filter(owner__in=users).values_list("pk", flat=True)} - {None}',
    'hubs.delete()',
    'BillingProfile.objects.filter(pk__in=profiles).delete()',
    'users.delete()',
    'left = BillingProfile.objects.filter(pk__in=profiles).count()',
    'if left:',
    '    raise RuntimeError(f"{left} billing profiles of the removed businesses and accounts left behind")',
  ].join('\n');

/** What a spec leaves behind: the businesses and the accounts whose email starts with its `prefix` (`e2e-<spec>-`). */
export function removeAccountsOf(prefix: string): void {
  djangoPrint(removingAccountsOf(prefix));
}

const execFileAsync = promisify(execFile);

/**
 * `djangoPrint` without blocking this process: the Hub the spec plays answers while `code` runs. For code that calls
 * it, such as a pass of `reconcile_hub_states`. A failing snippet rejects, its traceback in the error.
 */
export async function djangoPrintAsync(code: string): Promise<string> {
  const { stdout } = await execFileAsync('uv', ['run', 'python', '-c', `${DJANGO_BOOT}\n${code}`], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    encoding: 'utf8',
  });
  return stdout.trim();
}

let secretRead: Promise<string> | undefined;

/**
 * `INTERNAL_SHARED_SECRET` of the local SaaS (`.env`), to sign what the Hub would send: read once per worker, without
 * blocking this process. A spec that signs inside a test reads it first in a `beforeAll`, so that the Django boot of
 * the read is on no test's clock (saas#346).
 */
export function internalSecret(): Promise<string> {
  secretRead ??= djangoPrintAsync('from django.conf import settings;print(settings.INTERNAL_SHARED_SECRET)');
  return secretRead;
}

/** The Hub's callback (`POST /internal/hubs/{id}/ready`), as it sends it: the body names the hub of the path, signed. */
export async function reportBusinessReady(request: APIRequestContext, id: string): Promise<void> {
  const body = JSON.stringify({ id });
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac('sha256', await internalSecret()).update(`${timestamp}.${body}`).digest('hex');
  const ready = await request.post(`/internal/hubs/${id}/ready`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': String(timestamp), 'X-Erplora-Signature': signature },
  });
  expect(ready.status(), await ready.text()).toBe(200);
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

// ── Toasts ────────────────────────────────────────────────────────────────────────────────────

/**
 * The toasts that say `text`, the newest last: `shell/toast.ts` closes the one on screen as it presents the next, so
 * for a moment both are in the page, the new one still hidden. `.last()` is the one just shown; `toHaveCount(0)`, that
 * none is left (never `getByText`, which strict mode refuses while there are two).
 */
export function toast(page: Page, text: string | RegExp): Locator {
  return page.locator('ion-toast').filter({ hasText: text });
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

// ── Stripe, played by a spec ──────────────────────────────────────────────────────────────────
// Stripe cannot run in the e2e stack (no keys, no network to it): the page gets a double of Stripe.js
// (`playStripe`) and the operations that call Stripe are answered at the API's edge (`answerCheckoutStart`,
// `playStripePortal`), so a spec proves the page up to the `client_secret` request and the checkout's mount, never
// Stripe's own form, the webhook nor a real charge (`store-checkout.spec.ts` with `stripe listen` does).

/** What the page handed {@link playStripe}'s Stripe.js, and what it did with it. */
export interface StripePlayed {
  /** The publishable key of each `Stripe(key)`. */
  keys: string[];
  /** The `client_secret` of each Embedded Checkout created. */
  secrets: string[];
  /** The `data-testid` of the element each checkout was mounted in. */
  mountedIn: string[];
  /** How many checkouts the page destroyed. */
  destroyed: number;
}

/** The page's `window` once {@link playStripe} ran: what it recorded, and the `onComplete` of the last checkout. */
type StripeWindow = { __stripe: StripePlayed & { complete?: () => void } };

/**
 * Stripe.js as `page` would get it from js.stripe.com: it records what the page hands it ({@link stripeState}), mounts
 * a placeholder (`stripe-double`) where the Embedded Checkout goes and keeps its `onComplete` ({@link payInStripe}).
 */
export async function playStripe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    type Options = { fetchClientSecret: () => Promise<string>; onComplete?: () => void };
    const w = window as unknown as Record<string, unknown> & StripeWindow;
    w.__stripe = { keys: [], secrets: [], mountedIn: [], destroyed: 0 };
    w.Stripe = (key: string) => {
      w.__stripe.keys.push(key);
      return {
        async createEmbeddedCheckoutPage(options: Options) {
          w.__stripe.secrets.push(await options.fetchClientSecret());
          w.__stripe.complete = options.onComplete;
          return {
            mount(target: Element) {
              w.__stripe.mountedIn.push(target.getAttribute('data-testid') ?? '');
              const form = document.createElement('div');
              form.setAttribute('data-testid', 'stripe-double');
              form.textContent = 'Stripe Embedded Checkout (test double)';
              form.style.cssText = 'padding:48px 16px;border:1px dashed #999;border-radius:8px;text-align:center';
              target.append(form);
            },
            destroy() {
              w.__stripe.destroyed += 1;
            },
          };
        },
      };
    };
  });
}

/** What {@link playStripe}'s Stripe.js has recorded so far. */
export function stripeState(page: Page): Promise<StripePlayed> {
  return page.evaluate(() => {
    const { keys, secrets, mountedIn, destroyed } = (window as unknown as StripeWindow).__stripe;
    return { keys, secrets, mountedIn, destroyed };
  });
}

/** Stripe says the payment went through: the `onComplete` the page handed its last checkout runs, as Stripe.js does. */
export async function payInStripe(page: Page): Promise<void> {
  await page.evaluate(() => {
    const { complete } = (window as unknown as StripeWindow).__stripe;
    if (!complete) throw new Error('payInStripe: no Embedded Checkout was created with an onComplete');
    complete();
  });
}

/** What `billing.checkout.start` answers for a payment in Stripe's Embedded Checkout: a plan or an app on Free. */
const CHECKOUT = { flow: 'checkout', session_id: 'cs_test_e2e', client_secret: 'cs_test_e2e_secret', publishable_key: 'pk_test_e2e', preview: null };

/**
 * `billing.checkout.start` answered at the API's edge with `answer` (an Embedded Checkout's session by default): what
 * Stripe would open is never asked. Returns the bodies the page sent it, in order, as the page sent them.
 */
export async function answerCheckoutStart(page: Page, answer: object = CHECKOUT): Promise<unknown[]> {
  const started: unknown[] = [];
  await page.route('**/api/billing/checkout/start', async (route) => {
    started.push(route.request().postDataJSON());
    await route.fulfill({ json: answer });
  });
  return started;
}

/**
 * `path` opened where a business on Free pays in Stripe's Embedded Checkout: Stripe.js played ({@link playStripe}) and
 * `billing.checkout.start` answered with a checkout's session. Returns what the page started ({@link answerCheckoutStart}).
 */
export async function gotoWithCheckout(page: Page, path: string): Promise<unknown[]> {
  await playStripe(page);
  const started = await answerCheckoutStart(page);
  await page.goto(path);
  return started;
}

/**
 * The Store's apps of `business` (on Free) with the payment played ({@link gotoWithCheckout}), and «Add» of the paid
 * app `slug`: its payment opens in the checkout. Returns what the page started ({@link answerCheckoutStart}).
 */
export async function addAppInCheckout(page: Page, business: string, slug: string): Promise<unknown[]> {
  const started = await gotoWithCheckout(page, `/dashboard/store/modules?business=${business}`);
  await page.getByTestId(`module-${slug}`).getByTestId('module-add').click();
  return started;
}

/**
 * `path` opened where a business that already pays is charged in the panel's own dialog: `billing.checkout.start`
 * answers what is charged today (`amountDueCents`, `taxCents` of it), prorated now, and Stripe.js is never needed.
 * Returns what the page started ({@link answerCheckoutStart}).
 */
export async function gotoWithCharge(page: Page, path: string, amountDueCents: number, taxCents: number): Promise<unknown[]> {
  const preview = { amount_due_cents: amountDueCents, tax_cents: taxCents, currency: 'eur', proration_date: Math.floor(Date.now() / 1000), charge_starts_at: null };
  const started = await answerCheckoutStart(page, { flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview });
  await page.goto(path);
  return started;
}

/** Where `billing.portal.open` sends the page once {@link playStripePortal} plays it: Stripe's Customer Portal. */
export const STRIPE_PORTAL_URL = 'https://billing.stripe.com/p/session/e2e';

/**
 * Stripe's Customer Portal played: `billing.portal.open` answered with {@link STRIPE_PORTAL_URL}, and the page there a
 * placeholder. Returns the bodies the page sent `billing.portal.open`, in order.
 */
export async function playStripePortal(page: Page): Promise<unknown[]> {
  await page.route(/^https:\/\/billing\.stripe\.com\//, (route) =>
    route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Stripe (test double)</title><p>Stripe (test double)</p>' }),
  );
  const opened: unknown[] = [];
  await page.route('**/api/billing/portal', async (route) => {
    opened.push(route.request().postDataJSON());
    await route.fulfill({ json: { url: STRIPE_PORTAL_URL } });
  });
  return opened;
}

/**
 * `seedAccounts` without blocking this process (the same `demo_seed`, run by `djangoPrintAsync`): while it runs, what
 * lives in this process (the Hub or Stripe a spec plays, the timers) keeps answering, and a timeout can fire. A failing
 * seed rejects, its traceback in the error.
 */
export async function seedAccountsAsync(): Promise<void> {
  await djangoPrintAsync('from django.core.management import call_command\ncall_command("demo_seed")');
}

export const test = base.extend<{ signedInPage: Page }, { owner: Credentials }>({
  // Every page of a spec: no hot updates mid-spec (`freezeFrontend`).
  context: async ({ context }, use) => {
    await freezeFrontend(context);
    await use(context);
  },
  // Once per worker: the accounts exist before any spec signs in. Seeded without blocking Node (saas#358); as every
  // worker fixture, on a clock of its own (the project's timeout), never on the first test's.
  owner: [
    // Playwright reads a fixture's dependencies from its first parameter's pattern: none here.
    async ({}, use) => {
      await seedAccountsAsync();
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

/**
 * Every test of the spec, or of the `describe` it is called in, starts from the rows of `script` (`runSeed`) seeded
 * afresh, its page signed in as `account` through the API; once the last test has run, the rows go.
 */
export function seededAndSignedIn(script: string, account: Credentials): void {
  test.beforeEach(async ({ page }) => {
    runSeed(script, 'seed');
    await signIn(page.request, account);
  });
  test.afterAll(() => runSeed(script, 'clear'));
}

// ── A warm Django: one per worker, for what a test asks the SaaS's Django (saas#352) ──────────

const warm = new Map<string, Promise<WarmDjango>>();

/**
 * This worker's warm Django (`tests/e2e/panel/django_warm.py`, django-warm.ts) against the run's database (DEBUG on) with
 * `env` over it (`MAILING`): started on the first call and kept for the worker; another `env`, another process. A spec
 * awaits it in a `beforeAll` (its first `djangoPrintWarm` there does), so that its boot is on no test's clock.
 */
export function warmDjango(env: Readonly<Record<string, string>> = {}): Promise<WarmDjango> {
  const key = JSON.stringify(env);
  let django = warm.get(key);
  if (!django) {
    django = startWarm('uv', ['run', 'python', 'tests/e2e/panel/django_warm.py'], {
      cwd: SAAS_DIR,
      env: { ...djangoEnv(true), ...env },
    });
    warm.set(key, django);
  }
  return django;
}

/**
 * `djangoPrint` for inside a test: what `code` prints, run by this worker's warm Django (`warmDjango`), so the test pays
 * no Django boot and this process never blocks (saas#352). The same snippet reads the same values: each one runs as
 * `python -c` runs it after `django.setup()`; a failing one rejects with its traceback.
 */
export async function djangoPrintWarm(code: string, env: Readonly<Record<string, string>> = {}): Promise<string> {
  return (await warmDjango(env)).print(code);
}

/**
 * Who a spec's account is: a customer (`create_user`), Django's superuser (`create_superuser`), or a team account of
 * ERPlora (`accounts.services.create_platform_user`, with its group: the platform's admin or its support).
 */
export type AccountRole = 'customer' | 'superuser' | 'platform-admin' | 'platform-support';

export interface AccountOptions {
  role?: AccountRole;
  /** Its address proven (the default), as an account that signed in before; `false`, never proven. */
  verified?: boolean;
  firstName?: string;
  lastName?: string;
  /** The account's language (the panel speaks it once signed in); the model's own when left out. */
  language?: 'en' | 'es';
}

/** A fresh account of a spec, `email` with `password` and `options`, written by the warm Django: its credentials. */
export async function createAccountWarm(email: string, password: string, options: AccountOptions = {}): Promise<Credentials> {
  const { role = 'customer', verified = true, firstName, lastName, language } = options;
  const fields = Object.entries({ first_name: firstName, last_name: lastName, language }).filter(
    (field): field is [string, string] => field[1] !== undefined,
  );
  const said = (value: string) => JSON.stringify(value);
  const kwargs = [`email=${said(email)}`, `password=${said(password)}`, ...fields.map(([name, value]) => `${name}=${said(value)}`)];
  const group = role === 'platform-admin' ? 'services.PLATFORM_ADMIN' : 'services.PLATFORM_SUPPORT';
  const made =
    role === 'customer' || role === 'superuser'
      ? [`user = get_user_model().objects.${role === 'customer' ? 'create_user' : 'create_superuser'}(${kwargs.join(', ')})`]
      : [
          `user = services.create_platform_user(${said(email)}, ${group}, ${said(password)})[0]`,
          ...fields.map(([name, value]) => `user.${name} = ${said(value)}`),
          `user.save(update_fields=[${fields.map(([name]) => said(name)).join(', ')}])`,
        ];
  await djangoPrintWarm(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      'from accounts import services',
      ...made,
      `EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": ${verified ? 'True' : 'False'}, "primary": True})`,
    ].join('\n'),
  );
  return { email, password };
}

/** `removeAccountsOf` through the warm Django: the businesses and the accounts whose email starts with `prefix`. */
export async function removeAccountsWarm(prefix: string): Promise<void> {
  await djangoPrintWarm(removingAccountsOf(prefix));
}

/** A mail as a mail client reads it (Python's `email`): its type, the types of its parts, its HTML and its text. */
export interface MailParts {
  type: string;
  parts: string[];
  html: string;
  text: string;
}

/**
 * The newest mail to `to` written in the panel's mail folder from `since` on whose subject has `subject`, read from its
 * file as a mail client reads it, by the warm Django's Python (what the person sees, painted with `setContent`).
 */
export async function mailPartsOf(to: string, since: number, subject: string): Promise<MailParts> {
  const read = [
    'import email, json, pathlib',
    'from email import policy',
    `folder, to, since, subject = pathlib.Path(${JSON.stringify(PANEL_MAIL_DIR)}), ${JSON.stringify(to)}, ${since / 1000 - 0.05}, ${JSON.stringify(subject)}`,
    'found = None',
    'for path in sorted((p for p in folder.iterdir() if p.is_file() and p.stat().st_mtime >= since), key=lambda p: p.stat().st_mtime):',
    '    for raw in path.read_text().split("\\n" + "-" * 79 + "\\n")[:-1]:',
    '        message = email.message_from_string(raw, policy=policy.default)',
    '        if to in str(message["To"]) and subject.lower() in str(message["Subject"]).lower():',
    '            found = message',
    'assert found is not None, f"no mail to {to} with {subject!r} in {folder}"',
    'print(json.dumps({"type": found.get_content_type(), "parts": [part.get_content_type() for part in found.iter_parts()],',
    '    "html": found.get_body(preferencelist=("html",)).get_content(), "text": found.get_body(preferencelist=("plain",)).get_content()}))',
  ].join('\n');
  return JSON.parse(await djangoPrintWarm(read)) as MailParts;
}

// ── A spec's seeds by the warm Django (saas#355) ──────────────────────────────────────────────

/**
 * `runSeed` for inside a test (or a `beforeEach`): `tests/e2e/panel/<script> <args…>` run as its command line runs it
 * (as `__main__`, with its `sys.argv`) by this worker's warm Django for `env` (`warmDjango`), so the test pays no Django
 * boot and this process never blocks (saas#355); the last line it printed. A seed that exits with a reason rejects.
 */
export async function runSeedWarm(
  script: string,
  args: string | readonly string[],
  env: Readonly<Record<string, string>> = {},
): Promise<string> {
  const argv = JSON.stringify([`tests/e2e/panel/${script}`, ...[args].flat()]);
  const out = await djangoPrintWarm(
    [
      'import runpy, sys',
      'argv, path = sys.argv, list(sys.path)',
      `sys.argv = ${argv}`,
      'try:',
      '    runpy.run_path(sys.argv[0], run_name="__main__")',
      'except SystemExit as exited:',
      '    if exited.code not in (None, 0): raise',
      'finally:',
      '    sys.argv, sys.path[:] = argv, path',
    ].join('\n'),
    env,
  );
  return out.split('\n').at(-1) ?? '';
}

/**
 * `seededAndSignedIn` with every test's seed run by the warm Django (`runSeedWarm`): every test of the spec, or of the
 * `describe` it is called in, starts from the rows of `script` seeded afresh, its page signed in as `account` through
 * the API; once the last test has run, the rows go. The warm Django starts in a `beforeAll`, on no test's clock.
 */
export function seededAndSignedInWarm(script: string, account: Credentials): void {
  test.beforeAll(() => warmDjango());
  test.beforeEach(async ({ page }) => {
    await runSeedWarm(script, 'seed');
    await signIn(page.request, account);
  });
  test.afterAll(() => runSeedWarm(script, 'clear'));
}

// ── The real Hub's Django, asked by a spec (saas#354) ─────────────────────────────────────────

/**
 * What `code` prints in the real Hub's Django (`HUB_DIR`, its database `HUB_DB_NAME`; README «El Hub real de la e2e»), by
 * its `manage.py shell`: its last line. It never blocks this process, so a test's timeout still fires while it runs.
 */
export async function realHubPrint(code: string): Promise<string> {
  const { stdout } = await execFileAsync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], {
    cwd: process.env.HUB_DIR,
    // The Hub's database: never this run's DB_NAME, which the SaaS's stack.ts refuses.
    env: { ...process.env, DB_NAME: process.env.HUB_DB_NAME, DEBUG: 'True' },
    encoding: 'utf8',
  });
  return stdout.trim().split('\n').pop() ?? '';
}

// ── The Hub stack's databases, read by a spec (saas#370) ──────────────────────────────────────

/** A business of the Hub's stack, as `base_hub.slug` names it (`a`, `b`: its local hubs). */
const HUB_SLUG = /^[a-z0-9][a-z0-9-]*$/;
const HUB_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * The rows `query` reads in the Hub's stack on `port` (whatsapp-hub.spec.ts's header; the Postgres of the root's
 * compose.yaml), trimmed, by `psql` in that container without blocking this process: in its control database
 * (`hub_e2e_<port>`, the registry `base_hub`), or with `hub` in that business's own database (its `db_name` there),
 * where every app's tables live. A failing query rejects with what `psql` said.
 */
export async function hubStackSql(port: number, query: string, hub?: string): Promise<string> {
  let database = `hub_e2e_${port}`;
  if (hub !== undefined) {
    if (!HUB_SLUG.test(hub)) throw new Error(`hubStackSql: ${JSON.stringify(hub)} is no slug of a business`);
    database = await hubStackSql(port, `select db_name from base_hub where slug = '${hub}'`);
    expect(database, `the database of ${hub} in hub_e2e_${port}`).toMatch(new RegExp(`^hub_e2e_${port}_[0-9a-f]+$`));
  }
  const { stdout } = await execFileAsync(
    'docker',
    ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', database, '-At', '-c', query],
    { cwd: resolve(SAAS_DIR, '..'), encoding: 'utf8' },
  );
  return stdout.trim();
}

/** The Hub's own ids of its local hubs `a` and `b` in its stack on `port`: two UUIDs, or the call fails saying so. */
export async function hubStackIds(port: number): Promise<[string, string]> {
  const rows = await hubStackSql(port, "select slug || '=' || id from base_hub where slug in ('a', 'b') order by slug");
  const ids = Object.fromEntries(rows.split('\n').map((row) => row.split('=')));
  const found: [string, string] = [ids.a, ids.b];
  expect(found, `the ids of a and b in hub_e2e_${port}`).toEqual([expect.stringMatching(HUB_ID), expect.stringMatching(HUB_ID)]);
  return found;
}
