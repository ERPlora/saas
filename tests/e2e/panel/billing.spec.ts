// Billing (`/billing/:tab`, plan 2026-10-13 L3-C front; mockups `billing.html`) in Chrome, against the panel's
// own Django (project.ts) and the rows of billing_seed.py. Stripe and the platform hub do not run here: the
// spec plays Stripe's pages (the invoice page «Pay» goes to, the Customer Portal) and the platform hub's PDF at
// their boundaries, and leaves everything else to the real server — the invoices, the subscriptions, «Pay»
// (`billing.invoice.pay`), the 404 of a PDF not issued yet, the CSV, the billing details and their VIES check.
import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page, Request } from '@playwright/test';

import { djangoEnv } from '../django-env';
import {
  apiPost,
  businessIdOf,
  djangoPrint,
  expect,
  panelAccount,
  qaAccount,
  repeatedTop,
  settled,
  shot,
  signIn,
  test,
  VIEWPORTS,
  watchPageErrors,
} from './fixtures';
import { HUB_DOUBLE_PORT } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SHOTS_DIR = process.env.SHOTS_DIR ?? '/tmp/l3b2-shots';
mkdirSync(SHOTS_DIR, { recursive: true });

const BILLING = qaAccount('BILLING', panelAccount('billing'));
/** The widths of the mockups' screenshots (`billing-default-<width>-<theme>.png`). */
const WIDTHS = [390, 834, 1024, 1180, 1280, 1440] as const;

function seedBilling(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/billing_seed.py', action], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

// Every test starts from the same rows (some pay, edit or cancel), signed in again.
test.beforeEach(async ({ page }) => {
  seedBilling('seed');
  await signIn(page.request, BILLING);
});
test.afterAll(() => seedBilling('clear'));

const toast = (page: Page, text: string | RegExp) => page.locator('ion-toast').filter({ hasText: text });

/** Stripe's pages, played: whatever the browser opens there is a placeholder page. */
async function playStripePages(page: Page): Promise<void> {
  await page.route(/^https:\/\/(invoice|billing)\.stripe\.com\//, (route) =>
    route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Stripe (test double)</title><p>Stripe (test double)</p>' }),
  );
}

/** The ids of the seeded invoices, by Stripe's number (what the server lists as `reference`). */
async function invoiceIds(page: Page): Promise<Record<string, string>> {
  const response = await page.request.get('/api/billing/invoices?limit=50');
  expect(response.status()).toBe(200);
  const rows = ((await response.json()) as { rows: Array<{ id: string; reference: string }> }).rows;
  return Object.fromEntries(rows.map((row) => [row.reference, row.id]));
}

/** What waits for a payment for business `name`: its line of the grouped notice (two or more unpaid, audit R-15). */
const banner = (page: Page, name: string) => page.getByTestId('unpaid-group-item').filter({ hasText: name });

/** Picks `option` in the `ion-select` hooked as `testid` (an Ionic popover). */
async function pick(page: Page, testid: string, option: string): Promise<void> {
  await page.getByTestId(testid).click();
  await page.locator('ion-popover ion-radio').filter({ hasText: option }).click();
}

/** What scrolls sideways on the page on screen (as viewports.spec.ts reads it). */
async function sidewaysScroll(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const found: string[] = [];
    const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');
    if (scroll && scroll.scrollWidth > scroll.clientWidth + 1) found.push(`ion-content ${scroll.scrollWidth} > ${scroll.clientWidth}`);
    for (const table of shown.querySelectorAll<HTMLElement>('.data-table__scroll')) {
      if (table.scrollWidth > table.clientWidth + 1) found.push(`data-table ${table.scrollWidth} > ${table.clientWidth}`);
      if (table.classList.contains('data-table__scroll--overflow')) found.push('data-table__scroll--overflow');
    }
    return found;
  });
}

/**
 * Row actions painted over the previous column: a DataTable's actions box wider than its cell (the cell is the
 * track the table sized; the buttons it holds must fit in it). The sideways scroll cannot see it: the box
 * overflows towards the start.
 */
async function actionsOverflow(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    return [...shown.querySelectorAll<HTMLElement>('.data-table__row--data .data-table__cell--actions')].flatMap((cell) => {
      const box = cell.querySelector<HTMLElement>('.data-table__actions');
      const buttons = [...(box?.children ?? [])].map((child) => child.getBoundingClientRect()).filter((rect) => rect.width > 0);
      if (!buttons.length) return [];
      const left = Math.min(...buttons.map((rect) => rect.left));
      const room = cell.getBoundingClientRect().left;
      return left < room - 1 ? [`${cell.closest('[data-id]')?.getAttribute('data-id')}: buttons from ${Math.round(left)} < cell ${Math.round(room)}`] : [];
    });
  });
}

test.describe('billing', () => {
  test('Invoices: every business’s invoices, what waits for a payment, «Issuing» without its PDF, filters', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/billing');
    await expect(page).toHaveURL(/\/billing\/invoices$/);
    await expect(page.getByTestId('billing-lead')).toHaveText(
      'What you pay ERPlora for all your businesses. The invoices of your sales are inside each business.',
    );
    await expect(page.getByTestId('invoices-row')).toHaveCount(4);
    const ids = await invoiceIds(page);
    // Not collected: Stripe's reference until it is paid, «Pay» on the row.
    const norte = page.locator(`[data-testid="invoices-row"][data-id="${ids['E2ENORTE-0001']}"]`);
    await expect(norte).toContainText('E2ENORTE-0001');
    await expect(norte).toContainText('Not collected');
    await expect(norte.getByTestId(`invoices-row-${ids['E2ENORTE-0001']}-pay`)).toBeEnabled();
    // Paid and issued: its PDF; paid and still being issued: «Issuing», no PDF yet.
    const issued = page.locator(`[data-testid="invoices-row"][data-id="${ids['E2EBAKERY_AUG-0001']}"]`);
    await expect(issued).toContainText('ERP-2026-90071');
    await expect(issued).toContainText('Paid');
    await expect(issued.getByTestId(`invoices-row-${ids['E2EBAKERY_AUG-0001']}-pdf`)).toBeVisible();
    const issuing = page.locator(`[data-testid="invoices-row"][data-id="${ids['E2EBAKERY_SEP-0001']}"]`);
    await expect(issuing).toContainText('Issuing');
    await expect(issuing.getByTestId(`invoices-row-${ids['E2EBAKERY_SEP-0001']}-pdf`)).toHaveCount(0);
    // What waits for a payment: two invoices, one notice (audit R-15), each business on its line, days only.
    const group = page.getByTestId('billing-unpaid-group');
    await expect(group).toContainText('2 unpaid invoices: €72.58');
    await expect(banner(page, 'Bar La Plaza')).toContainText(/Bar La Plaza is suspended on \w{3} \d{1,2}, \d{4} if it is not paid \(€36\.29\)\./);
    await expect(banner(page, 'Bar La Plaza')).toContainText('The bank declined the card.');
    await expect(banner(page, 'Bar Norte')).toContainText('Bar Norte is suspended on');
    expect(await group.innerText()).not.toMatch(/\d{1,2}:\d{2}/);
    await page.screenshot({ path: join(SHOTS_DIR, 'billing-past-due-1280-light.png'), fullPage: true });
    // Filters: one «Filters» control of the toolbar (a popover, nothing from the bottom): the business in a
    // popover select, the status in a segment; kept in the address and counted on the button.
    const norteId = await businessIdOf(page.request, 'Bar Norte');
    await page.getByTestId('invoices-filters').click();
    await pick(page, 'invoices-business', 'Bar Norte');
    await expect(page).toHaveURL(new RegExp(`business=${norteId}`));
    await expect(page.getByTestId('invoices-row')).toHaveCount(1);
    await page.getByTestId('invoices-status').locator('ion-segment-button').filter({ hasText: 'Paid' }).click();
    await expect(page).toHaveURL(/status=paid/);
    await expect(page.getByTestId('invoices-filters-count')).toHaveText('2');
    await expect(page.locator('ion-action-sheet')).toHaveCount(0);
    // Escape closes the topmost overlay: wait until the business select's own popover has gone, or under load
    // it is still leaving and takes the Escape (a race of the test, seen in full runs).
    await expect(page.locator('ion-popover.select-popover')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('invoices-filters-panel')).toBeHidden();
    await expect(page.getByTestId('invoices-empty')).toContainText('No invoice matches the search or the filters');
    await page.getByTestId('invoices-show-all').click();
    await expect(page.getByTestId('invoices-row')).toHaveCount(4);
    // A business of the address that is not the account's: every invoice, saying so (W-F15).
    await page.goto('/billing/invoices?business=00000000-0000-7000-8000-000000000000');
    await expect(page.getByTestId('invoices-unknown-business')).toBeVisible();
    await expect(page.getByTestId('invoices-row')).toHaveCount(4);
    // A business on Free has none (X-18).
    await page.goto(`/billing/invoices?business=${await businessIdOf(page.request, 'Café Central')}`);
    await expect(page.getByTestId('invoices-empty')).toContainText('Café Central is on Free: it has no invoices.');
    expect(errors).toEqual([]);
  });

  test('PDF: the one issued comes from the platform hub; the one being issued is a 404 and says «Issuing»', async ({ page }) => {
    const asked: string[] = [];
    const hub: Server = createServer((request, response) => {
      asked.push(`${request.method} ${request.url}`);
      if (request.method === 'GET' && /^\/internal\/platform\/invoices\/[0-9a-f-]+\/pdf$/.test(request.url ?? '')) {
        response.writeHead(200, { 'Content-Type': 'application/pdf' });
        response.end('%PDF-1.7\n% ERPlora e2e\n%%EOF\n');
        return;
      }
      response.writeHead(503, { 'Content-Type': 'application/json' });
      response.end('{"error":{"code":"hub_away"}}');
    });
    await new Promise<void>((listening) => hub.listen(HUB_DOUBLE_PORT, '127.0.0.1', () => listening()));
    try {
      await page.goto('/billing/invoices');
      const ids = await invoiceIds(page);
      const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId(`invoices-row-${ids['E2EBAKERY_AUG-0001']}-pdf`).click()]);
      expect(download.suggestedFilename()).toBe('ERP-2026-90071.pdf');
      const path = await download.path();
      expect(execFileSync('head', ['-c', '8', path]).toString()).toBe('%PDF-1.7');
      expect(asked).toEqual([`GET /internal/platform/invoices/${ids['E2EBAKERY_AUG-0001']}/pdf`]);
      // Still being issued: the server answers 404 until the platform hub issues it.
      const notYet = await page.request.get(`/api/billing/invoices/pdf?id=${ids['E2EBAKERY_SEP-0001']}`);
      expect(notYet.status()).toBe(404);
      expect(((await notYet.json()) as { error: { code: string } }).error.code).toBe('billing.invoice_not_issued');
      // Selected, it counts only the issued ones (audit 2 S-01): this one has no PDF yet, said above the list.
      const selectRow = (id: string) => page.locator(`[data-testid="invoices-row"][data-id="${id}"] ion-checkbox`);
      await selectRow(ids['E2EBAKERY_SEP-0001']).click();
      await expect(page.getByTestId('invoices-pdf-selected')).toHaveText('Download PDF (0)');
      await expect(page.getByTestId('invoices-pdf-selected')).toHaveAttribute('aria-disabled', 'true');
      await expect(page.getByTestId('invoices-selection-note')).toHaveText(
        '1 selected invoice is still being issued: its PDF is ready in a few minutes.',
      );
      await page.screenshot({ path: join(SHOTS_DIR, 'billing-selected-1280-light.png') });
    } finally {
      await new Promise<void>((closed) => {
        hub.closeAllConnections();
        hub.close(() => closed());
      });
    }
  });

  test('PDF and CSV refused (R-05): a toast says why, the action waits, and no `.json` is ever saved', async ({ page }) => {
    const saved: string[] = [];
    page.on('download', (download) => saved.push(download.suggestedFilename()));
    await page.goto('/billing/invoices');
    const ids = await invoiceIds(page);
    const issued = page.getByTestId(`invoices-row-${ids['E2EBAKERY_AUG-0001']}-pdf`);
    // The platform hub away (nobody listens on the Hub's port): the server answers 503.
    await issued.click();
    await expect(toast(page, 'The invoice service is not answering. Try again in a moment.')).toBeVisible();
    // The platform hub has no PDF of it yet: 404 «still being issued», and its «Download PDF» waits.
    await page.route(/\/api\/billing\/invoices\/pdf\?/, (route) =>
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'billing.invoice_not_issued', message: 'This invoice is still being issued.' } }),
      }),
    );
    await issued.click();
    await expect(toast(page, 'This invoice is still being issued: its PDF will be ready as soon as it finishes.')).toBeVisible();
    await expect(issued.locator('button')).toBeDisabled();
    // The CSV refused the same way: said, not saved.
    await page.route(/\/api\/billing\/invoices\/csv/, (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'service_unavailable', message: 'The service is not answering.' } }),
      }),
    );
    await page.getByTestId('invoices-csv').click();
    await expect(toast(page, 'The service is not answering.')).toBeVisible();
    expect(saved).toEqual([]);
  });

  // flow: BILLING-F22 (FIX-SAAS-BILLING-INVOICE-DOWNLOAD-NETWORK-ERROR-ENGLISH). The network drops when the file is
  // asked for (the page is already there): the toast says so in the account's language, never «Network error
  // (Failed to fetch)», and nothing is saved.
  test('BILLING-F22 without network: «Descargar PDF» and «Descargar Excel» say so in Spanish and save nothing', async ({ page }) => {
    const offline = 'No hemos podido conectar con ERPlora. Revisa tu conexión e inténtalo de nuevo.';
    const saved: string[] = [];
    page.on('download', (download) => saved.push(download.suggestedFilename()));
    const errors = watchPageErrors(page);
    // A Spanish account (the seed's speaks English; the next test's seed sets it back).
    expect((await apiPost(page.request, '/api/accounts/preferences', { language: 'es' })).status()).toBe(200);
    await page.goto('/billing/invoices');
    const ids = await invoiceIds(page);
    await page.route(/\/api\/billing\/invoices\/(pdf\?|csv)/, (route) => route.abort('internetdisconnected'));
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      // «Descargar PDF» of the invoice's page.
      await page.goto(`/billing/invoices/${ids['E2EBAKERY_AUG-0001']}`);
      await expect(page.getByTestId('invoice-pdf')).toHaveText('Descargar PDF');
      await page.getByTestId('invoice-pdf').click();
      await expect(toast(page, offline)).toBeVisible();
      await expect(page.locator('ion-toast')).not.toContainText('Network error');
      await settled(page);
      await page.screenshot({ path: shot(`FIX-SAAS-BILLING-INVOICE-DOWNLOAD-NETWORK-ERROR-ENGLISH-${viewport.width}`) });
      // «Descargar Excel» of the list, the same way.
      await page.goto('/billing/invoices');
      await expect(page.getByTestId('invoices-row')).toHaveCount(4);
      await page.getByTestId('invoices-csv').click();
      await expect(toast(page, offline)).toBeVisible();
    }
    expect(saved).toEqual([]);
    expect(errors).toEqual([]);
  });

  test('«Download Excel»: the CSV of what the filters show, ready for Excel', async ({ page }) => {
    await page.goto('/billing/invoices?status=paid');
    await expect(page.getByTestId('invoices-row')).toHaveCount(2);
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('invoices-csv').click()]);
    expect(download.suggestedFilename()).toMatch(/^erplora-invoices-\d{4}-\d{2}-\d{2}\.csv$/);
    const csv = execFileSync('cat', [await download.path()]).toString('utf8');
    expect(csv.startsWith('﻿')).toBe(true);
    const lines = csv.slice(1).trim().split(/\r?\n/);
    expect(lines[0]).toBe('Invoice,Date,Business,Tax base,VAT,Total,Currency,Payment,Status');
    expect(lines.slice(1).map((line) => line.split(',')[0]).sort()).toEqual(['ERP-2026-90071', 'ERP-2026-90098']);
  });

  test('«Pay»: after a declined card it waits for another; otherwise it pays once at Stripe and, back, «Invoice paid»', async ({ page }) => {
    await playStripePages(page);
    const paid: Request[] = [];
    await page.route('**/api/billing/invoices/pay', async (route) => {
      paid.push(route.request());
      await new Promise((later) => setTimeout(later, 1500));
      await route.continue();
    });
    await page.goto('/billing/invoices');
    const ids = await invoiceIds(page);
    // Bar La Plaza: the bank declined the card — «Change card» first, «Pay» waits, saying why.
    const plaza = banner(page, 'Bar La Plaza');
    await expect(plaza.getByTestId('unpaid-group-change-card')).toBeVisible();
    await expect(plaza.getByTestId('pay-invoice').locator('button')).toBeDisabled();
    await expect(plaza.getByTestId('unpaid-group-why')).toHaveText('Change the card first: we do not charge the card the bank declined again.');
    await expect(page.getByTestId(`invoices-row-${ids['E2EPLAZA-0001']}-pay`).locator('button')).toBeDisabled();
    // Bar Norte: «Pay» → «Paying…» (every «Pay» waits) → Stripe's page of that invoice, asked once.
    const pay = banner(page, 'Bar Norte').getByTestId('pay-invoice');
    await expect(pay).toHaveText('Pay the invoice · €36.29');
    await pay.click();
    await expect(pay).toHaveText('Paying…');
    await expect(pay.locator('button')).toBeDisabled();
    await page.screenshot({ path: join(SHOTS_DIR, 'billing-paying-1280-light.png') });
    await page.waitForURL('https://invoice.stripe.com/i/e2e-billing-norte');
    expect(paid).toHaveLength(1);
    expect(paid[0].postDataJSON()).toEqual({ id: ids['E2ENORTE-0001'] });
    // Stripe charged it: the webhook numbers it (played here with the ORM) and, back in Billing, it says so.
    djangoPrint(
      [
        'from django.utils import timezone',
        'from billing.models import Invoice',
        `Invoice.objects.filter(stripe_invoice_id="in_e2e_billing_norte").update(payment_status="paid", number="ERP-2026-90120", series="ERP", sequence=90120, issued_on=timezone.localdate(), paid_at=timezone.now(), fiscal_status="issuing")`,
      ].join('\n'),
    );
    await page.goto('/billing/invoices');
    await expect(toast(page, 'Invoice paid: Bar Norte is up to date again')).toBeVisible();
    await expect(banner(page, 'Bar Norte')).toHaveCount(0);
    await page.screenshot({ path: join(SHOTS_DIR, 'billing-paid-1280-light.png') });
  });

  test('«Change card» opens Stripe’s Customer Portal of that payer (web only)', async ({ page }) => {
    await playStripePages(page);
    const opened: unknown[] = [];
    // The Portal is Stripe's: the server's call to it is played (no Stripe keys here).
    await page.route('**/api/billing/portal', async (route) => {
      opened.push(route.request().postDataJSON());
      await route.fulfill({ json: { url: 'https://billing.stripe.com/p/session/e2e' } });
    });
    await page.goto('/billing/invoices');
    await banner(page, 'Bar La Plaza').getByTestId('unpaid-group-change-card').click();
    await page.waitForURL('https://billing.stripe.com/p/session/e2e');
    expect(opened).toEqual([{ hub_id: await businessIdOf(page.request, 'Bar La Plaza') }]);
  });

  test('Subscriptions: one row per business, the server’s actions, «Cancel plan» of that business with Free’s limits', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/billing/subscriptions');
    await expect(page.getByTestId('subscriptions-row')).toHaveCount(3);
    await expect(page.getByTestId('billing-unpaid-text')).toHaveText('2 unpaid invoices: €72.58.');
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const plaza = await businessIdOf(page.request, 'Bar La Plaza');
    const bakeryRow = page.locator(`[data-testid="subscriptions-row"][data-id="${bakery}"]`);
    await expect(bakeryRow).toContainText('E2E Bill Bookings · €9.00/month + VAT');
    await expect(bakeryRow).toContainText('€47.18');
    // Each row leads with what the server put first: «Change plan», or «View the invoice» with an unpaid one.
    await expect(bakeryRow.getByTestId(`subscriptions-row-${bakery}-lead`)).toHaveText('Change plan');
    await expect(page.getByTestId(`subscriptions-row-${plaza}-lead`)).toHaveText('View the invoice');
    // One button per row and its «⋮» (Ioan, 2026-10-14): «View invoices» lives in the menu, with «Cancel plan».
    await expect(bakeryRow.locator(`[data-testid^="subscriptions-row-${bakery}-"]`)).toHaveCount(2);
    await expect(bakeryRow.getByTestId(`subscriptions-row-${bakery}-view_invoices`)).toHaveCount(0);
    await settled(page);
    expect(await sidewaysScroll(page)).toEqual([]);
    expect(await actionsOverflow(page)).toEqual([]);
    await page.screenshot({ path: join(SHOTS_DIR, 'billing-past-due-subscriptions-1280-light.png'), fullPage: true });
    // «Cancel plan»: about that business, its dates, its module and what Free covers for its people.
    await page.getByTestId(`subscriptions-row-${bakery}-menu`).click();
    await page.getByTestId(`subscriptions-row-${bakery}-cancel_plan`).click();
    const dialog = page.getByTestId('cancel-plan');
    await expect(dialog).toContainText('Cancel the plan');
    await expect(dialog).toContainText('Panadería López · Starter');
    await expect(dialog).toContainText('E2E Bill Bookings turns off on');
    await expect(dialog).toContainText('Free covers 3 users and 1 device at a time. Panadería López has 1 person, within that limit: nothing changes for the team.');
    await page.screenshot({ path: join(SHOTS_DIR, 'billing-default-subscriptions-cancel-1280-light.png') });
    await page.getByTestId('cancel-plan-cancel').click();
    await expect(dialog).toBeHidden();
    // «View the invoice» of a business that owes one: Invoices, that business, not collected.
    await page.getByTestId(`subscriptions-row-${plaza}-lead`).click();
    await expect(page).toHaveURL(new RegExp(`/billing/invoices\\?business=${plaza}&status=open$`));
    await expect(page.getByTestId('invoices-row')).toHaveCount(1);
    // «Change plan»: the Store, with that business.
    await page.goto('/billing/subscriptions');
    await page.getByTestId(`subscriptions-row-${bakery}-lead`).click();
    await expect(page).toHaveURL(new RegExp(`/store/plans\\?business=${bakery}$`));
    expect(errors).toEqual([]);
  });

  test('Payment details: the card (Stripe away says so) and the billing details, edited with their VIES check', async ({ page }) => {
    await page.goto('/billing/payment');
    // No Stripe here: the server says it cannot show the card now, never invents one.
    await expect(page.getByTestId('payment-card-detail')).toHaveText('We cannot show the card right now: try again in a few minutes.');
    await expect(page.getByTestId('profile-name')).toHaveText('Panadería López S.L.');
    await expect(page.locator('.kv')).toContainText('B12345678');
    await expect(page.locator('.kv')).toContainText('C/ Mayor 12, 28013 Madrid');
    await page.getByTestId('profile-edit').click();
    await expect(page.getByTestId('vies-status')).toHaveText('Valid tax ID.');
    await page.screenshot({ path: join(SHOTS_DIR, 'billing-default-payment-profile-1280-light.png') });
    await page.getByTestId('details-city').locator('input').fill('Getafe');
    await page.getByTestId('billing-profile-submit').click();
    await expect(toast(page, 'Billing details saved')).toBeVisible();
    await expect(page.locator('.kv')).toContainText('C/ Mayor 12, 28013 Getafe');
    // With Stripe answering (played): the card, its last failure and «Change card» as the main action.
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const plaza = await businessIdOf(page.request, 'Bar La Plaza');
    await page.route('**/api/billing/payment-method', (route) =>
      route.fulfill({
        json: {
          methods: [
            {
              businesses: [{ id: bakery, name: 'Panadería López' }, { id: plaza, name: 'Bar La Plaza' }],
              card: { brand: 'visa', last4: '4242', exp_month: 8, exp_year: 2028 },
              unavailable: false,
              last_failure: { at: '2026-10-10T08:00:00Z', business: 'Bar La Plaza' },
            },
          ],
        },
      }),
    );
    await page.reload();
    await expect(page.getByTestId('payment-card')).toHaveText('Visa •••• 4242');
    await expect(page.getByTestId('payment-failed')).toContainText('The last charge failed');
    await expect(page.getByTestId('payment-change')).toHaveText('Change card');
    await expect(page.getByTestId('profile-name')).toHaveText('Panadería López S.L.');
    await page.screenshot({ path: join(SHOTS_DIR, 'billing-card-payment-1280-light.png'), fullPage: true });
  });

  test('inside the apps and on the account surface: to look at, not to pay', async ({ page }) => {
    const stripe: string[] = [];
    page.on('request', (request) => {
      if (/stripe\.com/.test(request.url())) stripe.push(request.url());
    });
    await page.goto('/billing/invoices?surface=account');
    await expect(page.getByTestId('invoices-row')).toHaveCount(4);
    await expect(page.getByTestId('pay-invoice')).toHaveCount(0);
    await expect(page.locator('[data-testid$="-pay"]')).toHaveCount(0);
    await expect(page.getByTestId('unpaid-group-change-card')).toHaveCount(0);
    // Already in the browser (the account the app opens): why, not «go to erplora.com in your browser» (audit 2 S-09).
    await expect(page.getByTestId('unpaid-group-app')).toHaveText('This account was opened from the app: invoices are not paid from here.');
    await page.setViewportSize({ width: 390, height: 844 });
    // flow: ninguno — FIX tests/e2e. A capture right after a resize must be the page as painted at the new size.
    await settled(page);
    const png = await page.screenshot({ path: join(SHOTS_DIR, 'billing-default-mobile-390-light.png'), fullPage: true });
    expect(await repeatedTop(page, png), 'billing-default-mobile-390-light.png repeats the top of the page at its bottom').toBe(0);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/billing/subscriptions');
    await expect(page.getByTestId('subscriptions-app-hint')).toHaveText('This account was opened from the app: plans are not changed nor cancelled from here.');
    // Only what looks: «View the invoice» and «View invoices»; nothing changes or cancels a plan, no «⋮».
    await expect(page.locator('[data-testid^="subscriptions-row-"][data-testid$="-lead"]')).toHaveText(['View the invoice', 'View the invoice']);
    await expect(page.locator('[data-testid^="subscriptions-row-"][data-testid$="-menu"]')).toHaveCount(0);
    await page.goto('/billing/payment');
    await expect(page.getByTestId('payment-app')).toHaveText('This account was opened from the app: the card is not changed from here.');
    await expect(page.getByTestId('payment-change')).toHaveCount(0);
    await expect(page.getByTestId('profile-edit')).toBeVisible();
    expect(await page.locator('ion-router-outlet a[href*="stripe"]').count()).toBe(0);
    // Back to the web for the rest of the session; then the Tauri bridge (the installed apps).
    await page.goto('/billing/invoices?surface=web');
    await expect(page.getByTestId('pay-invoice').first()).toBeVisible();
    await page.addInitScript(() => {
      (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    });
    await page.goto('/billing/invoices');
    await expect(page.getByTestId('invoices-row')).toHaveCount(4);
    await expect(page.getByTestId('pay-invoice')).toHaveCount(0);
    expect(stripe).toEqual([]);
  });

  for (const width of WIDTHS) {
    const themes = width === 390 || width === 1440 ? (['light', 'dark'] as const) : (['light'] as const);
    for (const theme of themes) {
      test(`every tab at ${width} px (${theme}): no sideways scroll, no error`, async ({ page }) => {
        const errors = watchPageErrors(page);
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: width <= 390 ? 844 : width <= 834 ? 1112 : 900 });
        const ready: Record<string, string> = { invoices: 'invoices-row', subscriptions: 'subscriptions-row', payment: 'profile-name' };
        for (const [tab, hook] of Object.entries(ready)) {
          await page.goto(`/billing/${tab}`);
          await expect(page.getByTestId(hook).first()).toBeVisible();
          // What waits for a payment is live: on top of every tab once the stream answers.
          await expect(page.getByTestId(tab === 'invoices' ? 'billing-unpaid-group' : 'billing-unpaid-text').first()).toBeVisible();
          await settled(page);
          expect(await sidewaysScroll(page), `${tab} at ${width}`).toEqual([]);
          expect(await actionsOverflow(page), `${tab} at ${width}: actions over the previous column`).toEqual([]);
          const section = tab === 'invoices' ? '' : `-${tab}`;
          await page.screenshot({ path: join(SHOTS_DIR, `billing-default${section}-${width}-${theme}.png`), fullPage: true });
        }
        expect(errors).toEqual([]);
      });
    }
  }
});
