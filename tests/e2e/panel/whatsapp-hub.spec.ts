// flow: WHATSAPP-G03, WHATSAPP-G07 — WhatsApp's cross e2e on a REAL Hub (its doors since hub#127): Meta → erplora.com
// → the Hub's «WhatsApp» inbox, nothing played. erplora.com (this checkout) pushes the snapshot of `a` with its
// `whatsapp` key (door 4) to the Hub, which takes it; then the spec plays only Meta: a customer's message, the owner's
// reply from the phone app and Meta's «read», each signed as Meta signs its webhook, posted to erplora.com, which
// hands them to the Hub (doors 1 and 2); the owner sees them arrive in the open inbox without a reload, in three sizes.
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
//     WHATSAPP_APP_ID=… WHATSAPP_APP_SECRET=… WHATSAPP_VERIFY_TOKEN=… WHATSAPP_CONFIG_ID=… (project.ts WHATSAPP_E2E) \
//     uv run python manage.py runserver 127.0.0.1:<port+1>
// Then: `env -u DB_NAME E2E_SAAS_PORT=<base> VITE_DEV_PORT=<vite> E2E_CROSS_HUB_PORT=<port> E2E_MAIL_DIR=<mail dir>
// pnpm e2e:ci tests/e2e/panel/whatsapp-hub.spec.ts`. The spec seeds erplora.com's side itself (whatsapp_hub_seed.py:
// `a` and `b` with the Hub's ids, `a`'s number) and names what it writes in the Hub `e2e.…`.
import { execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { readMailCode } from '@erplora/ui/testing/mail';
import { expect, type Page, test } from '@playwright/test';

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

test.skip(!HUB_PORT || !MAIL_DIR, 'needs a real Hub stack and its SaaS (E2E_CROSS_HUB_PORT, E2E_MAIL_DIR): see the header');
test.describe.configure({ mode: 'serial' });

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

/** erplora.com's side of the run, and the snapshot of `a` pushed to the Hub: what the seed printed. */
function seedErplora(): { delivered: boolean; hub_error: string } {
  const out = execFileSync('uv', ['run', 'python', 'tests/e2e/panel/whatsapp_hub_seed.py', ...hubIds()], {
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

/** The owner opens the inbox of `a`: the Hub sends them to erplora.com, which asks the password and the mailed code. */
async function openInbox(page: Page): Promise<void> {
  await page.goto(INBOX);
  await page.waitForURL((url) => url.origin === SAAS, { timeout: 30_000 });
  await expect(page.getByTestId('login-form')).toBeVisible({ timeout: 30_000 });
  const since = Date.now();
  await submitSignInForm(page, OWNER);
  await expect(page).toHaveURL(/\/verify-email(\?|$)/);
  await page.getByTestId('code').locator('input').fill(await readMailCode({ dir: MAIL_DIR, to: OWNER.email, since }));
  await page.getByTestId('verify-email-submit').click();
  await page.waitForURL(INBOX, { timeout: 30_000 });
}

const shown = (page: Page) => page.locator('.ion-page:not(.ion-page-hidden)').last();

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
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: shot(`APP-WHATSAPP-WHATSAPP-G07-${viewport.width}`) });
  }
});
