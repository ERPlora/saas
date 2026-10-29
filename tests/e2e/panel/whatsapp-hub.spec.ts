// flow: WHATSAPP-G03, WHATSAPP-G07 — WhatsApp's cross e2e on a REAL Hub (its doors since hub#127): Meta → erplora.com
// → the Hub's «WhatsApp» inbox, nothing played. erplora.com (this checkout) pushes the snapshot of `a` with its
// `whatsapp` key (door 4) to the Hub, which takes it; then the spec plays only Meta: a customer's message, the owner's
// reply from the phone app and Meta's «read», each signed as Meta signs its webhook, posted to erplora.com, which
// hands them to the Hub (doors 1 and 2); the owner sees them arrive in the open inbox without a reload, in three sizes.
// flow: ninguno propio — desbloquea WHATSAPP_INBOX-F13 (tope), F27 y F28 del Hub
// (FIX-SAAS-WHATSAPP-E2E-SEED-TEMPLATES-AND-USAGE): the seed's templates (what erplora.com keeps after reading Meta's
// list) reach the Hub's Settings with Meta's verdict and reason, and with the month at the plan's allowance
// (`--used`) the Hub says so and «Send» stops.
//
// It needs the Hub's stack and, beside it, a SaaS of this checkout (the CI has no Hub: there it is skipped, and says
// so). From a Hub checkout (`<port>` = E2E_CROSS_HUB_PORT, e.g. 8440; tests/e2e/README.md of the Hub):
//   DB_NAME=hub_e2e_<port> node tests/e2e/database.ts
//   E2E_HUB_PORT=<port> VITE_DEV_PORT=<vite> SAAS_URL=http://localhost:<port+1> DB_NAME=hub_e2e_<port> \
//     uv run python manage.py runserver 127.0.0.1:<port>
// From this checkout (its own database, never the shared `saas`):
//   env -u DB_NAME E2E_SAAS_PORT=<port+1> node tests/e2e/database.ts
//   DB_NAME=saas_e2e_<port+1> VITE_DEV_PORT=<vite+1> HUB_INTERNAL_URL=http://127.0.0.1:<port> \
//     HUB_CALLBACK_TEMPLATE='http://{slug}.localhost:<port>/auth/callback' EMAIL_FILE_PATH=<mail dir> \
//     WHATSAPP_MEDIA_BASE_URL=http://localhost:<port+1> (the only origin of attachments the Hub takes: its SAAS_URL) \
//     WHATSAPP_APP_ID=… WHATSAPP_APP_SECRET=… WHATSAPP_VERIFY_TOKEN=… WHATSAPP_CONFIG_ID=… (project.ts WHATSAPP_E2E) \
//     uv run python manage.py runserver 127.0.0.1:<port+1>
// Then: `env -u DB_NAME E2E_SAAS_PORT=<base> VITE_DEV_PORT=<vite> E2E_CROSS_HUB_PORT=<port> E2E_MAIL_DIR=<mail dir>
// pnpm e2e:ci tests/e2e/panel/whatsapp-hub.spec.ts`. The spec seeds erplora.com's side itself (whatsapp_hub_seed.py:
// `a` and `b` with the Hub's ids, `a`'s number, its templates and the month's usage) and names what it writes in the
// Hub `e2e.…`; it leaves the month's usage at 0.
import { execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { readMailCode } from '@erplora/ui/testing/mail';
import { expect, type Locator, type Page, test } from '@playwright/test';

import { horizontalOverflow } from '../horizontal-overflow';
import { OWNER, shot, submitSignInForm, VIEWPORTS } from './fixtures';
import { WHATSAPP_E2E } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const REPO_DIR = resolve(SAAS_DIR, '..');
const HUB_PORT = Number(process.env.E2E_CROSS_HUB_PORT ?? 0);
const MAIL_DIR = process.env.E2E_MAIL_DIR ?? '';
const HUB_A = `http://a.localhost:${HUB_PORT}`;
const SAAS = `http://localhost:${HUB_PORT + 1}`;
const INBOX = `${HUB_A}/whatsapp_inbox/inbox`;
/** whatsapp_hub_seed.py's number of `a` and its WhatsApp Business account. */
const NUMBER_ID = '880000000000101';
const WABA_ID = '880000000000100';
const BUSINESS_PHONE = '34910000101';
/** whatsapp_hub_seed.py's templates of `a` (its TEMPLATES, as Meta's list gives them). */
const SEEDED = {
  approved: 'e2e_seed_recordatorio_cita',
  inReview: 'e2e_seed_oferta_color',
  rejected: 'e2e_seed_cambio_horario',
  photo: 'e2e_seed_bienvenida_foto',
} as const;
const TASK = 'FIX-SAAS-WHATSAPP-E2E-SEED-TEMPLATES-AND-USAGE';

test.skip(!HUB_PORT || !MAIL_DIR, 'needs a real Hub stack and its SaaS (E2E_CROSS_HUB_PORT, E2E_MAIL_DIR): see the header');
// Each test may sign in on a stack just started (FIRST_LOAD on both servers).
test.describe.configure({ mode: 'serial', timeout: 240_000 });

/** One query in the Hub's stack database: its rows, trimmed. */
function hubSql(query: string): string {
  return execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', `hub_e2e_${HUB_PORT}`, '-At', '-c', query],
    { cwd: REPO_DIR, encoding: 'utf8' },
  ).trim();
}

/** The Hub's own ids of its local hubs `a` and `b`, read in its stack's database. */
function hubIds(): [string, string] {
  const rows = hubSql("select slug || '=' || id from base_hub where slug in ('a', 'b') order by slug");
  const ids = Object.fromEntries(rows.split('\n').map((row) => row.split('=')));
  return [ids.a, ids.b];
}

/** erplora.com's side of the run, and the snapshot of `a` pushed to the Hub: what the seed printed (`--used N`: the
 *  month's usage of `a`, 0 when not given). */
function seedErplora(...options: string[]): { delivered: boolean; hub_error: string } {
  const out = execFileSync('uv', ['run', 'python', 'tests/e2e/panel/whatsapp_hub_seed.py', ...hubIds(), ...options], {
    cwd: SAAS_DIR,
    encoding: 'utf8',
    env: { ...process.env, DEBUG: 'True', DB_NAME: `saas_e2e_${HUB_PORT + 1}`, HUB_INTERNAL_URL: `http://127.0.0.1:${HUB_PORT}` },
  });
  return JSON.parse(out.trim().split('\n').at(-1) ?? '{}');
}

/** One change of Meta's webhook for `a`'s number, as Meta posts it. */
function notice(field: 'messages' | 'smb_message_echoes', value: Record<string, unknown>): string {
  return JSON.stringify({
    object: 'whatsapp_business_account',
    entry: [
      {
        id: WABA_ID,
        changes: [
          {
            field,
            value: {
              messaging_product: 'whatsapp',
              metadata: { display_phone_number: BUSINESS_PHONE, phone_number_id: NUMBER_ID },
              ...value,
            },
          },
        ],
      },
    ],
  });
}

const now = () => String(Math.floor(Date.now() / 1000));

/** Posts `body` to erplora.com's webhook signed as Meta signs it (`X-Hub-Signature-256`, the e2e app's secret). */
async function meta(page: Page, body: string): Promise<number> {
  const signature = `sha256=${createHmac('sha256', WHATSAPP_E2E.appSecret).update(body).digest('hex')}`;
  const answer = await page.request.post(`${SAAS}/webhooks/whatsapp/`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': signature },
  });
  return answer.status();
}

/** How long the first page of each server may take: a stack just started has its Vite build the SPA on that load. */
const FIRST_LOAD = 90_000;

/** The owner opens the inbox of `a`: the Hub sends them to erplora.com, which asks the password and the mailed code. */
async function openInbox(page: Page): Promise<void> {
  await page.goto(INBOX);
  await page.waitForURL((url) => url.origin === SAAS, { timeout: FIRST_LOAD });
  await expect(page.getByTestId('login-form')).toBeVisible({ timeout: FIRST_LOAD });
  const since = Date.now();
  await submitSignInForm(page, OWNER);
  await expect(page).toHaveURL(/\/verify-email(\?|$)/);
  await page.getByTestId('code').locator('input').fill(await readMailCode({ dir: MAIL_DIR, to: OWNER.email, since }));
  await page.getByTestId('verify-email-submit').click();
  await page.waitForURL(INBOX, { timeout: FIRST_LOAD });
}

const shown = (page: Page) => page.locator('.ion-page:not(.ion-page-hidden)').last();

/** No horizontal scroll in the page at its current size. */
const fits = async (page: Page) => (await horizontalOverflow(page)) === 0;

/** `target` brought into sight at the page's new size, again if the page painted it anew meanwhile. */
async function inSight(target: Locator): Promise<void> {
  await expect(async () => {
    await target.scrollIntoViewIfNeeded({ timeout: 2_000 });
    await expect(target).toBeInViewport({ timeout: 2_000 });
  }).toPass({ timeout: 15_000 });
}

test.afterAll(() => {
  // The month's usage back to 0: a spec after this one sends again.
  if (HUB_PORT && MAIL_DIR) expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
});

test('WHATSAPP-G03: the snapshot erplora.com pushes carries the connected number, and the real Hub takes it', async ({ page }) => {
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });

  await openInbox(page);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-search] input')).toBeVisible();
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-not-connected]')).toBeHidden();
});

test('WHATSAPP-G07: a customer’s message, the owner’s reply from the phone and her «read» reach the open inbox through erplora.com', async ({
  page,
}) => {
  const customer = `3469901${String(Math.floor(Math.random() * 1e4)).padStart(4, '0')}`;
  const name = `e2e.Ana ${Date.now().toString(36)}`;
  const run = Date.now();

  await openInbox(page);
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(customer.slice(2));
  await page.evaluate(() => {
    (window as unknown as { e2eNoReload: boolean }).e2eNoReload = true;
  });
  const row = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: customer.slice(2) });

  // Meta → erplora.com → door 1: her message, with her WhatsApp name.
  const message = notice('messages', {
    contacts: [{ profile: { name }, wa_id: customer }],
    messages: [{ from: customer, id: `e2e.wamid.${run}.in`, timestamp: now(), type: 'text', text: { body: 'Hola, ¿me dais cita el viernes?' } }],
  });
  expect(await meta(page, message)).toBe(200);
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText(name);
  await expect(row.locator('[data-testid=whatsapp-inbox-unread]')).toHaveText('1');

  await row.click();
  const panel = shown(page).locator('[data-testid=whatsapp-inbox-detail]');
  const bubbles = (side: 'inbound' | 'outbound') => panel.locator(`[data-testid=whatsapp-inbox-message][data-side=${side}]`);
  await expect(bubbles('inbound')).toHaveCount(1);
  await expect(bubbles('inbound')).toContainText('¿me dais cita el viernes?');

  // The owner answers from the WhatsApp Business app: Meta's echo → door 1, a message of the business, «Sent».
  const echo = `e2e.wamid.${run}.echo`;
  const echoed = notice('smb_message_echoes', {
    message_echoes: [{ from: BUSINESS_PHONE, to: customer, id: echo, timestamp: now(), type: 'text', text: { body: 'Sí, el viernes a las 10:00.' } }],
  });
  expect(await meta(page, echoed)).toBe(200);
  const reply = bubbles('outbound').filter({ hasText: 'el viernes a las 10:00' });
  await expect(reply).toBeVisible({ timeout: 30_000 });
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-from-phone]')).toBeVisible();

  // Meta says she read it → door 2: «Read».
  const read = notice('messages', { statuses: [{ id: echo, status: 'read', timestamp: now(), recipient_id: customer }] });
  expect(await meta(page, read)).toBe(200);
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Read', { timeout: 30_000 });
  expect(await page.evaluate(() => (window as unknown as { e2eNoReload?: boolean }).e2eNoReload === true)).toBe(true);

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Read');
    expect(await horizontalOverflow(page)).toBe(0);
    await page.screenshot({ path: shot(`APP-WHATSAPP-WHATSAPP-G07-${viewport.width}`) });
  }
});

// flow: ninguno propio — desbloquea WHATSAPP_INBOX-F13 (tope), F27 y F28 del Hub
test(`${TASK}: the real Hub lists the templates erplora.com keeps and, with the month spent, «Send» stops`, async ({
  page,
}) => {
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  await openInbox(page);

  // F27 and F28: Settings lists what erplora.com read from Meta, each with Meta's verdict, a rejected one with its reason.
  await page.goto(`${HUB_A}/whatsapp_inbox/settings`);
  const table = 'whatsapp-inbox-templates';
  await shown(page).locator(`[data-testid=${table}-search] input`).fill('e2e_seed');
  const row = (name: string) => shown(page).locator(`[data-testid=${table}-row]`, { hasText: name });
  await expect(row(SEEDED.approved)).toContainText('Approved', { timeout: 30_000 });
  await expect(row(SEEDED.inReview)).toContainText('In review');
  await expect(row(SEEDED.rejected)).toContainText('Rejected');
  await expect(row(SEEDED.rejected)).toContainText('INVALID_FORMAT');
  await expect(row(SEEDED.photo)).toContainText('Approved');
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await inSight(row(SEEDED.rejected));
    expect(await fits(page)).toBe(true);
    await page.screenshot({ path: shot(`${TASK}-${viewport.width}`) });
  }

  // F13: the month at the plan's allowance (the figure erplora.com's snapshot gave the Hub) is said in Settings.
  const limit = Number(hubSql("select monthly_limit from whatsapp_inbox_channel where host = 'a'"));
  expect(limit).toBeGreaterThan(0);
  expect(seedErplora('--used', String(limit))).toEqual({ delivered: true, hub_error: '' });
  const month = shown(page).locator('[data-testid=whatsapp-inbox-settings-month]');
  await expect(month).toContainText(`${limit} of ${limit} messages sent`, { timeout: 30_000 });

  // A customer still writes (the cap only limits what is sent), but «Send» says why instead of sending.
  await page.goto(INBOX);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-cap-reached]')).toContainText(
    'You have used all the WhatsApp messages of your plan this month.',
  );
  const customer = `3469901${String(Math.floor(Math.random() * 1e4)).padStart(4, '0')}`;
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(customer.slice(2));
  const message = notice('messages', {
    contacts: [{ profile: { name: `e2e.Marta ${Date.now().toString(36)}` }, wa_id: customer }],
    messages: [{ from: customer, id: `e2e.wamid.${Date.now()}.cap`, timestamp: now(), type: 'text', text: { body: '¿Me dais cita el lunes?' } }],
  });
  expect(await meta(page, message)).toBe(200);
  const conversation = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: customer.slice(2) });
  await expect(conversation).toBeVisible({ timeout: 30_000 });
  await conversation.click();
  const panel = shown(page).locator('[data-testid=whatsapp-inbox-detail]');
  const blocked = panel.locator('[data-testid=whatsapp-inbox-composer-blocked]');
  await expect(blocked).toHaveAttribute('data-code', 'cap_reached');
  await expect(panel.locator('[data-testid=whatsapp-inbox-composer-send]')).toHaveJSProperty('disabled', true);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await inSight(blocked);
    expect(await fits(page)).toBe(true);
    await page.screenshot({ path: shot(`${TASK}-cap-${viewport.width}`) });
  }
});

// flow: WHATSAPP-F05 (rechazo por tope del mes)
const CAP_TASK = 'FIX-SAAS-WHATSAPP-CAP-REFUSAL-DOES-NOT-PUSH-USAGE';
test(`${CAP_TASK}: WHATSAPP-F05 — a send erplora.com refuses at the cap tells the real Hub the month's usage`, async ({
  page,
}) => {
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  const usage = () => hubSql("select monthly_usage from whatsapp_inbox_channel where host = 'a'");
  const limit = Number(hubSql("select monthly_limit from whatsapp_inbox_channel where host = 'a'"));
  expect(limit).toBeGreaterThan(0);
  // erplora.com's month at the allowance while the Hub was told 0 (its snapshot behind): the Hub still offers «Send».
  expect(seedErplora('--used', String(limit), '--behind')).toEqual({ delivered: true, hub_error: '' });
  expect(usage()).toBe('0');

  await openInbox(page);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-cap-reached]')).toBeHidden();
  const customer = `3469901${String(Math.floor(Math.random() * 1e4)).padStart(4, '0')}`;
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(customer.slice(2));
  const message = notice('messages', {
    contacts: [{ profile: { name: `e2e.Olga ${Date.now().toString(36)}` }, wa_id: customer }],
    messages: [{ from: customer, id: `e2e.wamid.${Date.now()}.f05`, timestamp: now(), type: 'text', text: { body: '¿Abrís el domingo?' } }],
  });
  expect(await meta(page, message)).toBe(200);
  const conversation = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: customer.slice(2) });
  await expect(conversation).toBeVisible({ timeout: 30_000 });
  await conversation.click();
  await page.evaluate(() => {
    (window as unknown as { e2eNoReload: boolean }).e2eNoReload = true;
  });

  // The Hub hands the reply to erplora.com (door 5), which refuses it at the cap (the same 409 as ever)…
  const panel = shown(page).locator('[data-testid=whatsapp-inbox-detail]');
  await panel.locator('[data-testid=whatsapp-inbox-composer-text] textarea').fill('No, el domingo cerramos.');
  await panel.locator('[data-testid=whatsapp-inbox-composer-send]').click();
  const reply = panel.locator('[data-testid=whatsapp-inbox-message][data-side=outbound]', { hasText: 'el domingo cerramos' });
  await expect(reply.locator('[data-testid=whatsapp-inbox-message-error]')).toHaveAttribute(
    'data-code',
    'whatsapp_inbox.cap_reached',
    { timeout: 30_000 },
  );
  // …and, after its COMMIT, pushes the snapshot with the month's real usage: the open inbox stops offering «Send».
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-cap-reached]')).toContainText(
    'You have used all the WhatsApp messages of your plan this month.',
    { timeout: 30_000 },
  );
  const blocked = panel.locator('[data-testid=whatsapp-inbox-composer-blocked]');
  await expect(blocked).toHaveAttribute('data-code', 'cap_reached');
  await expect(panel.locator('[data-testid=whatsapp-inbox-composer-send]')).toHaveJSProperty('disabled', true);
  expect(usage()).toBe(String(limit));
  expect(await page.evaluate(() => (window as unknown as { e2eNoReload?: boolean }).e2eNoReload === true)).toBe(true);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await inSight(blocked);
    expect(await fits(page)).toBe(true);
    await page.screenshot({ path: shot(`${CAP_TASK}-${viewport.width}`) });
  }
});
