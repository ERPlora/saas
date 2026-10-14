// What the panel's specs start from: the seeded account (`manage.py demo_seed`), the sign-in
// (allauth.headless's API, or the real /login page when the sign-in is what a spec checks), the
// session /api/me reports, the three viewports, uncaught page errors and the evidence folder.
// Import `test` and `expect` from here, not from `@playwright/test`.
import { execFileSync } from 'node:child_process';
import { mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type APIRequestContext, type APIResponse, type BrowserContext, type Page, test as base, expect } from '@playwright/test';

import { HUB_DOUBLE_PORT, PANEL_MAIL_DIR } from './project';

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

/** Vite's hot-update socket (`server.hmr` of vite.config.ts; its path is `base`, with a token). */
const VITE_HMR = /^ws:\/\/localhost:5174\//;

/**
 * Cuts `context`'s pages off from Vite's hot updates: the socket opens, answered by the spec, and
 * nothing arrives. Another session saving a `.vue` mid-run (a shared component, DataTable) would
 * otherwise remount components under the spec and leave an open dialog behind. Every page load
 * still gets the files as they are on disk. The `context` of every panel spec already has it.
 */
export async function freezeFrontend(context: BrowserContext): Promise<void> {
  await context.routeWebSocket(VITE_HMR, () => {});
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

/**
 * What `code` prints, run with Django set up against the local database of `.env` (DEBUG on). For
 * what a spec reads from the SaaS's side and no page shows.
 */
export function djangoPrint(code: string): string {
  const boot = 'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings");django.setup()';
  return execFileSync('uv', ['run', 'python', '-c', `${boot}\n${code}`], {
    cwd: SAAS_DIR,
    env: { ...process.env, DEBUG: 'True' },
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

/** One mail as the file backend wrote it: who to, when (whole seconds) and its decoded text. */
interface Mail {
  to: string;
  sentAt: number;
  body: string;
}

/**
 * Every mail in `PANEL_MAIL_DIR`: a file per connection, each message closed by a line of 79 `-`.
 * What follows the last one is empty, or a message still being written: skipped until it closes.
 */
function readMails(): Mail[] {
  let files: string[];
  try {
    files = readdirSync(PANEL_MAIL_DIR);
  } catch {
    return []; // Nothing sent yet: the backend makes the folder with its first mail.
  }
  return files.flatMap((file) => readFileSync(join(PANEL_MAIL_DIR, file), 'utf8').split(/\r?\n-{79}\r?\n/).slice(0, -1).map(parseMail));
}

/** A single-part text mail (what Django's `send_mail` writes): headers, then the body in its encoding. */
function parseMail(raw: string): Mail {
  const split = raw.search(/\r?\n\r?\n/);
  const head = raw.slice(0, split).replace(/\r?\n[ \t]+/g, ' ');
  const headers = new Map(
    head.split(/\r?\n/).map((line) => {
      const colon = line.indexOf(':');
      return [line.slice(0, colon).trim().toLowerCase(), line.slice(colon + 1).trim()] as const;
    }),
  );
  if ((headers.get('content-type') ?? '').startsWith('multipart/')) {
    throw new Error(`a multipart mail to ${headers.get('to')}: teach parseMail its parts`);
  }
  const text = raw.slice(split).replace(/^\r?\n\r?\n/, '');
  return {
    to: headers.get('to') ?? '',
    sentAt: Date.parse(headers.get('date') ?? ''),
    body: decodeBody(text, (headers.get('content-transfer-encoding') ?? '7bit').toLowerCase()),
  };
}

function decodeBody(text: string, encoding: string): string {
  if (encoding === 'base64') return Buffer.from(text.replace(/\s+/g, ''), 'base64').toString('utf8');
  if (encoding !== 'quoted-printable') return text;
  const joined = text.replace(/=\r?\n/g, '');
  const bytes: number[] = [];
  for (let at = 0; at < joined.length; at += 1) {
    const hex = joined.slice(at + 1, at + 3);
    if (joined[at] === '=' && /^[0-9A-F]{2}$/i.test(hex)) {
      bytes.push(parseInt(hex, 16));
      at += 2;
    } else {
      bytes.push(joined.charCodeAt(at));
    }
  }
  return Buffer.from(bytes).toString('utf8');
}

/**
 * Waits for a mail to `to` sent from `since` on (a `Date.now()` taken before the action that sends
 * it) whose text matches `link`, and returns the first match: the link the person would click.
 * Earlier runs' mails stay in the folder and are skipped by date.
 */
export async function waitForMail(to: string, since: number, link: RegExp): Promise<string> {
  const from = Math.floor(since / 1000) * 1000; // The Date header has whole seconds.
  let found: string | undefined;
  await expect
    .poll(
      () => {
        const mail = readMails().find((one) => one.to === to && one.sentAt >= from && link.test(one.body));
        found = mail?.body.match(link)?.[0];
        return found;
      },
      { message: `a mail to ${to} with ${link} in ${PANEL_MAIL_DIR}`, timeout: 15_000 },
    )
    .toBeTruthy();
  return found as string;
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
const PLAYED = [/^PUT \/internal\/hubs\/[0-9a-f-]+\/state$/, /^POST \/internal\/sessions\/revoke$/];

/**
 * Plays the Hub on `HUB_DOUBLE_PORT`, where the panel's Django sends its calls (project.ts), until
 * `close()`: it records every call and acknowledges the snapshot push and the session revocation.
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
