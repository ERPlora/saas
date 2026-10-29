// flow: WHATSAPP-F01, WHATSAPP-F02, WHATSAPP-F11 — erplora.com's return page of Meta's window (Embedded Signup),
// `GET /whatsapp/return` (whatsapp/signup_return.py), and the Hub's doors 10–12 on a REAL Hub.
//
// The Hub opens Meta's window without Facebook's SDK (its WORKBOOK whatsapp_inbox, «La ventana de Meta sin el SDK de
// Facebook»): `window.open` of `https://www.facebook.com/<version>/dialog/oauth?…&redirect_uri=<door 10's>&state=
// <slug>.<32 hex>`. Meta ends the window by sending it to that redirect_uri with `?code=…&state=…` (or `?error=…`),
// and erplora.com's page posts `{type: 'erplora.whatsapp.signup', state, code | error, error_description}` to the
// window that opened Meta's, only at the origin of the hub the state names, and closes itself. Only Meta is played,
// here: its dialog answers by sending the window to the return page with a made-up code, as Meta does when the
// person finishes. What Meta posts meanwhile from facebook.com (`WA_EMBEDDED_SIGNUP`, the account and the number
// chosen) cannot be posted from another origin by a test: the Hub's Vitest proves how it takes it.
//
// Without a Hub (the CI): the window is opened from a page of the hubs' origin (`a`, served by the browser's route
// with the Hub's own Cross-Origin-Opener-Policy, `same-origin-allow-popups`): the page takes the code, or Meta's
// reason, the hub `b` does not, and a state that names no hub leaves the page open saying it can be closed (the
// three sizes: FIX-SAAS-WHATSAPP-EMBEDDED-SIGNUP-RETURN-<width>).
//
// With the real Hub (E2E_CROSS_HUB_PORT, E2E_MAIL_DIR; the stack of whatsapp-hub.spec.ts's header, its SaaS with
// `WHATSAPP_REDIRECT_URI=http://localhost:<port+1>/whatsapp/return`): F02, the owner disconnects `a`'s seeded number
// from the inbox's Settings and the Hub has erplora.com (door 12) disconnect it; F11 and F01, Settings asks
// erplora.com (door 10) what opens Meta's window, and that real page of the Hub, opening the window as its Settings
// does, gets the code back from erplora.com's origin with its attempt's state. The Hub only offers «Connect WhatsApp»
// with an https return page, so locally its button is not pressed: the window is opened from the page itself.
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { readMailCode } from '@erplora/ui/testing/mail';
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { horizontalOverflow } from '../horizontal-overflow';
import { OWNER, repeatedTop, settled, shot, submitSignInForm, VIEWPORTS } from './fixtures';
import { PANEL_URL, WHATSAPP_E2E } from './project';

const TASK = 'FIX-SAAS-WHATSAPP-EMBEDDED-SIGNUP-RETURN';
const RETURN_TYPE = 'erplora.whatsapp.signup';
const CLOSABLE = 'This window can be closed now.';
const CODE = 'AQBe2e-one-time-code_9';

/** What a page of the hub received by `postMessage` while Meta's window was open. */
interface Received {
  origin: string;
  data: Record<string, unknown>;
}

/** `page` in the three sizes, once `ready` holds in each, painted at that size and without sideways scroll. */
async function captures(page: Page, name: string, ready: () => Promise<void>): Promise<void> {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await ready();
    await settled(page);
    expect(await horizontalOverflow(page)).toBe(0);
    const png = await page.screenshot({ path: shot(`${name}-${viewport.width}`) });
    expect(await repeatedTop(page, png)).toBe(0);
  }
}

/** A state as the Hub writes it (`newState` of its lib/metaSignup.ts): the business and 16 random bytes in hex. */
const newState = (slug: string): string => `${slug}.${randomBytes(16).toString('hex')}`;

/** Meta's dialog as the Hub opens it (`dialogUrl` of its lib/metaSignup.ts). */
function dialogUrl(redirectUri: string, state: string): string {
  const url = new URL('https://www.facebook.com/v25.0/dialog/oauth');
  const params = {
    client_id: WHATSAPP_E2E.appId,
    config_id: WHATSAPP_E2E.configId,
    response_type: 'code',
    override_default_response_type: 'true',
    redirect_uri: redirectUri,
    state,
    display: 'popup',
    extras: JSON.stringify({ setup: {} }),
  };
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url.toString();
}

/** Meta, the only party played: its dialog sends the window back to its `redirect_uri` with `answer` and the state. */
async function playMeta(context: BrowserContext, answer: Record<string, string>): Promise<void> {
  await context.unroute('https://www.facebook.com/**');
  await context.route('https://www.facebook.com/**', async (route) => {
    const asked = new URL(route.request().url());
    const back = new URL(asked.searchParams.get('redirect_uri') ?? '');
    for (const [key, value] of Object.entries(answer)) back.searchParams.set(key, value);
    back.searchParams.set('state', asked.searchParams.get('state') ?? '');
    await route.fulfill({ status: 302, headers: { Location: back.toString() } });
  });
}

/** Opens Meta's window from `page` as the Hub's Settings does, waits until it closes itself and returns what `page`
 *  received meanwhile; `closes: false` when the window is expected to stay (it is returned open). */
async function openMetaWindow(page: Page, url: string, closes = true): Promise<{ received: Received[]; popup: Page }> {
  await page.evaluate(() => {
    const seen = window as unknown as { e2eReceived: Received[] };
    seen.e2eReceived = [];
    window.addEventListener('message', (event) => seen.e2eReceived.push({ origin: event.origin, data: event.data }));
  });
  const [popup] = await Promise.all([
    page.waitForEvent('popup'),
    page.evaluate((dialog) => {
      window.open(dialog, 'erplora-whatsapp-signup', 'popup,width=640,height=760');
    }, url),
  ]);
  if (closes) {
    await popup.waitForEvent('close', { timeout: 15_000 });
  } else {
    await expect(popup.getByTestId('whatsapp-return-closable')).toHaveText(CLOSABLE);
  }
  const received = await page.evaluate(() => (window as unknown as { e2eReceived: Received[] }).e2eReceived);
  return { received, popup };
}

test.describe('without a Hub: a page of the hubs’ origin opens Meta’s window', () => {
  // The panel's Django sends a hub's messages where its jumps go (HUB_CALLBACK_TEMPLATE, development's default).
  const template = process.env.HUB_CALLBACK_TEMPLATE ?? 'http://{slug}.localhost:8000/auth/callback';
  const hubOrigin = (slug: string) => new URL(template.replace('{slug}', slug)).origin;
  const returnPage = `${PANEL_URL}/whatsapp/return`;

  /** A page of `slug`'s origin, as the Hub's Settings: only the browser's route serves it, with the Hub's policy. */
  async function hubPage(page: Page, slug: string): Promise<void> {
    await page.route(`${hubOrigin(slug)}/**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'text/html',
        headers: { 'Cross-Origin-Opener-Policy': 'same-origin-allow-popups' },
        body: '<!doctype html><title>Settings</title><p>The inbox’s Settings</p>',
      }),
    );
    await page.goto(`${hubOrigin(slug)}/whatsapp_inbox/settings`);
  }

  test('WHATSAPP-F01: the one-time code goes back to the page that opened Meta’s window, and it closes', async ({
    page,
    context,
  }) => {
    await hubPage(page, 'a');
    const state = newState('a');
    await playMeta(context, { code: CODE });

    const { received } = await openMetaWindow(page, dialogUrl(returnPage, state));

    expect(received).toEqual([{ origin: new URL(PANEL_URL).origin, data: { type: RETURN_TYPE, state, code: CODE } }]);
  });

  test('WHATSAPP-F01: Meta’s refusal goes back with its reason', async ({ page, context }) => {
    await hubPage(page, 'a');
    const state = newState('a');
    await playMeta(context, { error: 'access_denied', error_description: 'Permissions error' });

    const { received } = await openMetaWindow(page, dialogUrl(returnPage, state));

    expect(received).toEqual([
      {
        origin: new URL(PANEL_URL).origin,
        data: { type: RETURN_TYPE, state, error: 'access_denied', error_description: 'Permissions error' },
      },
    ]);
  });

  test('WHATSAPP-F01: a code meant for another business never reaches this one', async ({ page, context }) => {
    await hubPage(page, 'a');
    await playMeta(context, { code: CODE });

    // The state names `b`: the message goes to b's origin only, and the page of `a` gets nothing.
    const { received } = await openMetaWindow(page, dialogUrl(returnPage, newState('b')));

    expect(received).toEqual([]);
  });

  test('WHATSAPP-F01: a state that names no business hands nothing back and says the window can be closed', async ({
    page,
    context,
  }) => {
    await hubPage(page, 'a');
    await playMeta(context, { code: CODE });
    const errors: string[] = [];
    context.on('page', (opened) => {
      opened.on('pageerror', (error) => errors.push(error.message));
      opened.on('console', (message) => {
        if (message.type() === 'error') errors.push(message.text());
      });
    });

    const { received, popup } = await openMetaWindow(page, dialogUrl(returnPage, `www.${'0'.repeat(32)}`), false);

    expect(received).toEqual([]);
    await captures(popup, TASK, () => expect(popup.getByTestId('whatsapp-return-closable')).toBeVisible());
    // No script refused by the CSP, nothing thrown.
    expect(errors).toEqual([]);
  });

  test('WHATSAPP-F01: opened by itself, the page only says it can be closed', async ({ page }) => {
    const answer = await page.goto(`${returnPage}?code=${CODE}&state=${newState('a')}`);

    expect(answer?.headers()['cross-origin-opener-policy']).toBe('unsafe-none');
    await expect(page.getByTestId('whatsapp-return-closable')).toHaveText(CLOSABLE);
  });
});

// With the real Hub of whatsapp-hub.spec.ts's stack.
const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const REPO_DIR = resolve(SAAS_DIR, '..');
const HUB_PORT = Number(process.env.E2E_CROSS_HUB_PORT ?? 0);
const MAIL_DIR = process.env.E2E_MAIL_DIR ?? '';
const HUB_A = `http://a.localhost:${HUB_PORT}`;
const SAAS = `http://localhost:${HUB_PORT + 1}`;
const SETTINGS = `${HUB_A}/whatsapp_inbox/settings`;

/** The Hub's own ids of its local hubs `a` and `b`, read in its stack's database. */
function hubIds(): [string, string] {
  const rows = execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', `hub_e2e_${HUB_PORT}`, '-At', '-c',
      "select slug || '=' || id from base_hub where slug in ('a', 'b') order by slug"],
    { cwd: REPO_DIR, encoding: 'utf8' },
  );
  const ids = Object.fromEntries(rows.trim().split('\n').map((row) => row.split('=')));
  return [ids.a, ids.b];
}

/** erplora.com's side of the run (whatsapp_hub_seed.py: `a` with its number) pushed to the Hub: what the seed printed. */
function seedErplora(): { delivered: boolean; hub_error: string } {
  const out = execFileSync('uv', ['run', 'python', 'tests/e2e/panel/whatsapp_hub_seed.py', ...hubIds()], {
    cwd: SAAS_DIR,
    encoding: 'utf8',
    env: { ...process.env, DEBUG: 'True', DB_NAME: `saas_e2e_${HUB_PORT + 1}`, HUB_INTERNAL_URL: `http://127.0.0.1:${HUB_PORT}` },
  });
  return JSON.parse(out.trim().split('\n').at(-1) ?? '{}');
}

/** The owner opens `url` of the hub `a`: the Hub sends them to erplora.com, which asks the password and the mailed code. */
async function openHub(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await page.waitForURL((at) => at.origin === SAAS, { timeout: 30_000 });
  await expect(page.getByTestId('login-form')).toBeVisible({ timeout: 30_000 });
  const since = Date.now();
  await submitSignInForm(page, OWNER);
  await expect(page).toHaveURL(/\/verify-email(\?|$)/);
  await page.getByTestId('code').locator('input').fill(await readMailCode({ dir: MAIL_DIR, to: OWNER.email, since }));
  await page.getByTestId('verify-email-submit').click();
  await page.waitForURL(url, { timeout: 30_000 });
}

const number = (page: Page) => page.locator('.ion-page:not(.ion-page-hidden)').last().getByTestId('whatsapp-inbox-number');

test.describe('with the real Hub', () => {
  test.skip(!HUB_PORT || !MAIL_DIR, 'needs a real Hub stack and its SaaS (E2E_CROSS_HUB_PORT, E2E_MAIL_DIR): see the header');
  test.describe.configure({ mode: 'serial' });

  test('WHATSAPP-F02: the owner disconnects the number from the Hub’s Settings and erplora.com disconnects it', async ({
    page,
  }) => {
    expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
    await openHub(page, SETTINGS);
    await expect(number(page)).toContainText('Connected');
    await expect(number(page)).toContainText('+34910000101');

    await number(page).getByTestId('whatsapp-inbox-number-disconnect').click();
    const dialog = page.getByTestId('whatsapp-inbox-number-disconnect-dialog');
    await expect(dialog).toBeVisible();
    const told = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/disconnect'));
    await page.getByTestId('whatsapp-inbox-number-disconnect-dialog-submit').click();

    // Door 12 of this checkout disconnected the number its seed gave `a`; the Hub says so at once.
    const answer = await told;
    expect((await answer.json()) as unknown).toEqual({ disconnected: true });
    await expect(number(page).getByTestId('whatsapp-inbox-number-done')).toHaveText('WhatsApp disconnected.');
    await expect(number(page)).toContainText('Not connected');
    await expect(number(page)).not.toContainText('+34910000101');
    await captures(page, `${TASK}-F02`, () => expect(number(page)).toContainText('Not connected'));
  });

  test('WHATSAPP-F11, WHATSAPP-F01: the Hub asks erplora.com what opens Meta’s window, and its page gets the code back', async ({
    page,
    context,
  }) => {
    const asked = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/channel/prepare'));
    await openHub(page, SETTINGS);

    // Door 10 of this checkout answered the real Hub with Meta's app of the run.
    const prepared = (await (await asked).json()) as Record<string, unknown>;
    expect(prepared).toMatchObject({ app_id: WHATSAPP_E2E.appId, config_id: WHATSAPP_E2E.configId, graph_version: 'v25.0' });
    await expect(number(page)).toContainText('Not connected');

    const state = newState('a');
    await playMeta(context, { code: CODE });
    const { received } = await openMetaWindow(page, dialogUrl(`${SAAS}/whatsapp/return`, state));

    // What the Hub's Settings takes (`readReturn` of its lib/metaSignup.ts): from the return page's origin, its state.
    expect(received).toEqual([{ origin: SAAS, data: { type: RETURN_TYPE, state, code: CODE } }]);
    await captures(page, `${TASK}-F01`, () => expect(number(page)).toContainText('Not connected'));
  });
});
