// Part 2 of billing (MIGRATION-TASK APP-BILLING-2): the paid apps in the Store and the pages of Billing, at the
// three sizes of the migration (390×844, 834×1112, 1440×900), against the panel's own Django and the rows of
// billing_apps_seed.py. As store.spec.ts, Stripe does not run here: the operations that call it
// (`billing.checkout.start` and `.confirm`, `billing.module.cancel`) are played at the API's edge, and Stripe.js
// is a double that mounts a placeholder; everything else is the real server. Each test names its flow by its
// registry key (BILLING-Gnn); in billing/WORKBOOK.md: G61=F31, G62=F32, G63=F09, G66=F33, G67=F34, G68=F35,
// G05=F36, G92=F22, G94=F23, G95=F08, G17=F11.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator, Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { businessIdOf, djangoPrint, expect, panelAccount, qaAccount, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const ACCOUNT = qaAccount('BILLING_APPS', panelAccount('billing-apps'));
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

function seed(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/billing_apps_seed.py', action], { cwd: SAAS_DIR, env: djangoEnv(true), stdio: 'pipe' });
}

test.beforeEach(async ({ page }) => {
  seed('seed');
  await signIn(page.request, ACCOUNT);
});
test.afterAll(() => seed('clear'));

const toast = (page: Page, text: string | RegExp) => page.locator('ion-toast').filter({ hasText: text });

/** `ready` at each size: no sideways scroll, a capture `APP-BILLING-2-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>, fullPage = true): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-BILLING-2-${key}-${size.name}`), fullPage });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/**
 * A dialog that slides in again at a new size (below 640px it is a sheet from the bottom) is in place once its
 * button `testid` is whole on screen and stays put for a frame: the slide runs in Ionic's shadow DOM, where
 * `settled` does not see it, and a capture taken before shows the sheet halfway.
 */
async function dialogInPlace(page: Page, testid: string): Promise<void> {
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

/** The amounts of a charge's summary in `dialog` that do not fit their row: cut off at the edge. */
async function cutAmounts(dialog: Locator): Promise<string[]> {
  return dialog.getByTestId('proration-row').evaluateAll((rows) =>
    rows.flatMap((row) => {
      const note = row.querySelector('ion-note');
      if (!note) return [];
      const box = row.getBoundingClientRect();
      const amount = note.getBoundingClientRect();
      const cut = amount.right > box.right + 0.5 || note.scrollWidth > note.clientWidth + 1;
      return cut ? [note.textContent?.trim() ?? ''] : [];
    }),
  );
}

/** What `billing.module.*` and `billing.checkout.confirm` answer: the business's subscription after the change. */
function subscriptionOut(hubId: string, modules: Array<{ slug: string; valid_until: string | null }>) {
  return {
    hub_id: hubId,
    plan: 'starter',
    billing_interval: 'month',
    status: 'active',
    cancel_at_period_end: false,
    current_period_end: null,
    trial_end: null,
    modules: modules.map((module) => ({ ...module, source: 'purchase' })),
  };
}

/** Stripe.js as the page would get it from js.stripe.com: mounts a placeholder and keeps `onComplete`. */
async function playStripe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    type Options = { fetchClientSecret: () => Promise<string>; onComplete?: () => void };
    const w = window as unknown as Record<string, unknown> & { __stripe: { complete?: () => void } };
    w.__stripe = {};
    w.Stripe = () => ({
      async createEmbeddedCheckoutPage(options: Options) {
        await options.fetchClientSecret();
        w.__stripe.complete = options.onComplete;
        return {
          mount(target: Element) {
            const form = document.createElement('div');
            form.setAttribute('data-testid', 'stripe-double');
            form.textContent = 'Stripe Embedded Checkout (test double)';
            form.style.cssText = 'padding:48px 16px;border:1px dashed #999;border-radius:8px;text-align:center';
            target.append(form);
          },
          destroy() {},
        };
      },
    });
  });
}

test.describe('billing part 2: paid apps and the pages of Billing', () => {
  test('BILLING-G61: the Store says what each paid app is in the business: had, cancelled, off sale or for sale', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.goto(`/dashboard/store/modules?business=${bakery}`);
    const bookings = page.getByTestId('module-e2e_apps_bookings');
    const reports = page.getByTestId('module-e2e_apps_reports');
    const loyalty = page.getByTestId('module-e2e_apps_loyalty');
    await atEverySize(page, 'BILLING-G61', async () => {
      await expect(bookings.getByTestId('module-owned')).toBeVisible();
      await expect(bookings.getByTestId('module-cancel')).toBeVisible();
      await expect(reports.getByTestId('module-off-sale')).toHaveText('No longer sold: you keep it while you pay it, and can cancel it whenever you want.');
      await expect(loyalty.getByTestId('module-add')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G62: a paying business adds a paid app with its proration, and it turns on', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.route('**/api/billing/checkout/start', (route) =>
      route.fulfill({ json: { flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: { amount_due_cents: 435, tax_cents: 76, currency: 'eur', proration_date: Math.floor(Date.now() / 1000), charge_starts_at: null } } }),
    );
    const confirmed: unknown[] = [];
    await page.route('**/api/billing/checkout/confirm', async (route) => {
      confirmed.push(route.request().postDataJSON());
      await route.fulfill({ json: subscriptionOut(bakery, [{ slug: 'e2e_apps_bookings', valid_until: null }, { slug: 'e2e_apps_loyalty', valid_until: null }]) });
    });
    await page.goto(`/dashboard/store/modules?business=${bakery}`);
    const loyalty = page.getByTestId('module-e2e_apps_loyalty');
    await loyalty.getByTestId('module-add').click();
    const dialog = page.getByTestId('proration-modal');
    await atEverySize(
      page,
      'BILLING-G62',
      async () => {
        await expect(dialog.getByTestId('proration-row').first()).toBeVisible();
        await dialogInPlace(page, 'proration-modal-submit');
        expect(await cutAmounts(dialog)).toEqual([]);
      },
      false,
    );
    await dialog.getByTestId('proration-modal-submit').click();
    await expect(toast(page, 'E2E Apps Loyalty added to Panadería López: it turns on in a few seconds')).toBeVisible();
    await expect(loyalty.getByTestId('module-activating')).toHaveText(/Activating… in Panadería López/);
    expect(confirmed).toEqual([expect.objectContaining({ hub_id: bakery, module: 'e2e_apps_loyalty' })]);
    expect(errors).toEqual([]);
  });

  test('BILLING-G63: on Free a paid app is paid in the secure checkout, and back from it the business says it turns on', async ({ page }) => {
    const errors = watchPageErrors(page);
    await playStripe(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const started: unknown[] = [];
    await page.route('**/api/billing/checkout/start', async (route) => {
      started.push(route.request().postDataJSON());
      await route.fulfill({ json: { flow: 'checkout', session_id: 'cs_test_e2e_apps', client_secret: 'cs_test_e2e_apps_secret', publishable_key: 'pk_test_e2e', preview: null } });
    });
    await page.goto(`/dashboard/store/modules?business=${cafe}`);
    await page.getByTestId('module-e2e_apps_bookings').getByTestId('module-add').click();
    await expect(page.getByTestId('checkout-modal').getByTestId('stripe-double')).toBeVisible();
    expect(started).toEqual([expect.objectContaining({ hub_id: cafe, module: 'e2e_apps_bookings' })]);
    await page.evaluate(() => (window as unknown as { __stripe: { complete: () => void } }).__stripe.complete());
    await expect(page).toHaveURL(new RegExp(`/dashboard/businesses/${cafe}/summary$`));
    await expect(toast(page, 'E2E Apps Bookings added to Café Central: it turns on in a few seconds')).toBeVisible();
    await atEverySize(page, 'BILLING-G63', async () => {
      await expect(page.getByTestId('summary-plan')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G66: «Cancel module» says until when it works, cancels it, and it can be kept until then', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const until = new Date(Date.now() + 18 * 86_400_000).toISOString();
    const cancelled: unknown[] = [];
    await page.route('**/api/billing/module/cancel', async (route) => {
      cancelled.push(route.request().postDataJSON());
      await route.fulfill({ json: subscriptionOut(bakery, [{ slug: 'e2e_apps_bookings', valid_until: until }, { slug: 'e2e_apps_reports', valid_until: null }]) });
    });
    await page.goto(`/dashboard/store/modules?business=${bakery}`);
    const bookings = page.getByTestId('module-e2e_apps_bookings');
    await bookings.getByTestId('module-cancel').click();
    const dialog = page.getByTestId('store-cancel-module');
    await atEverySize(
      page,
      'BILLING-G66',
      async () => {
        await expect(dialog).toContainText('E2E Apps Bookings keeps working in Panadería López until');
        await expect(dialog).toContainText('Nothing the business wrote with it is deleted.');
        await dialogInPlace(page, 'store-cancel-module-submit');
      },
      false,
    );
    await page.getByTestId('store-cancel-module-submit').click();
    await expect(toast(page, /E2E Apps Bookings cancelled: it works until/)).toBeVisible();
    await expect(bookings.getByTestId('module-keep')).toBeVisible();
    expect(cancelled).toEqual([{ hub_id: bakery, module: 'e2e_apps_bookings' }]);
    expect(errors).toEqual([]);
  });

  test('BILLING-G67: an app whose cancellation ended is for sale again; one still running says until when', async ({ page }) => {
    const errors = watchPageErrors(page);
    const norte = await businessIdOf(page.request, 'Bar Norte');
    await page.goto(`/dashboard/store/modules?business=${norte}`);
    await atEverySize(page, 'BILLING-G67', async () => {
      await expect(page.getByTestId('module-e2e_apps_bookings').getByTestId('module-add')).toBeVisible();
      await expect(page.getByTestId('module-e2e_apps_loyalty').getByTestId('module-cancelled')).toContainText('(cancelled)');
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G68: an app is taken to another business by cancelling it in one and adding it in the other', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const norte = await businessIdOf(page.request, 'Bar Norte');
    await page.goto(`/dashboard/store/modules?business=${bakery}`);
    await expect(page.getByTestId('module-e2e_apps_bookings').getByTestId('module-cancel')).toBeVisible();
    // The picker chooses the other business: there the same app is on sale.
    await page.goto(`/dashboard/store/modules?business=${norte}`);
    await atEverySize(page, 'BILLING-G68', async () => {
      await expect(page.getByTestId('store-business')).toHaveJSProperty('value', norte);
      await expect(page.getByTestId('module-e2e_apps_bookings').getByTestId('module-add')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G92: Invoices lists every invoice with «View invoice», and it opens its page', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/dashboard/billing/invoices');
    await atEverySize(page, 'BILLING-G92', async () => {
      await expect(page.getByText('ERP-2026-90201').first()).toBeVisible();
    });
    const row = page.locator('[data-testid^="invoices-row-"][data-testid$="-view"]').first();
    await row.click();
    await expect(page).toHaveURL(/\/dashboard\/billing\/invoices\/[0-9a-f-]+$/);
    await expect(page.getByTestId('invoice-title')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('BILLING-G05: the page of an invoice: its lines, totals and who it is made out to; a credit note links its invoice', async ({ page }) => {
    const errors = watchPageErrors(page);
    const [id, creditId] = djangoPrint(
      'from billing.models import Invoice\nfor number in ("ERP-2026-90201", "ERPR-2026-90007"): print(Invoice.objects.get(number=number).id)',
    ).split('\n');
    await page.goto(`/dashboard/billing/invoices/${id}`);
    await atEverySize(page, 'BILLING-G05', async () => {
      await expect(page.getByTestId('invoice-title')).toHaveText('Invoice ERP-2026-90201');
      await expect(page.getByTestId('invoice-line')).toHaveCount(2);
      await expect(page.getByTestId('invoice-totals')).toContainText('€30.72');
      await expect(page.getByTestId('invoice-recipient')).toContainText('Panadería López S.L.');
      await expect(page.getByTestId('invoice-pdf')).toBeVisible();
    });
    await page.goto('/dashboard/billing/invoices');
    await page.getByTestId(`invoices-row-${creditId}-view`).click();
    await expect(page.getByTestId('invoice-rectification')).toContainText('Credit note R1 · Duplicate charge');
    await page.getByTestId('invoice-rectified-link').click();
    // Ionic keeps the credit note's page under the invoice's: the one on screen is the last one not hidden.
    await expect(page).toHaveURL(new RegExp(`/dashboard/billing/invoices/${id}$`));
    await expect(page.locator('.ion-page:not(.ion-page-hidden)').last().getByTestId('invoice-title')).toHaveText('Invoice ERP-2026-90201');
    expect(errors).toEqual([]);
  });

  test('BILLING-G94: Subscriptions says the plan and the paid apps of each business, a cancelled one until when', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/dashboard/billing/subscriptions');
    await atEverySize(page, 'BILLING-G94', async () => {
      await expect(page.getByText('Bar Norte').first()).toBeVisible();
      await expect(page.getByText(/E2E Apps Reports/).first()).toBeVisible();
      await expect(page.getByText(/E2E Apps Loyalty/).first()).toBeVisible();
      // BILLING-G67: Bar Norte's Bookings ended yesterday and is gone; the bakery's is still had.
      await expect(page.getByText(/E2E Apps Bookings/).filter({ visible: true })).toHaveCount(1);
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G95: the plans and their prices, in the Store of a business on Free', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    await atEverySize(page, 'BILLING-G95', async () => {
      await expect(page.getByTestId('plan-free').getByTestId('plan-current')).toBeVisible();
      await expect(page.getByTestId('plan-starter').getByTestId('plan-upgrade')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G17: a paying business changes plan with what it is charged today', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.route('**/api/billing/checkout/start', (route) =>
      route.fulfill({ json: { flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: { amount_due_cents: 1452, tax_cents: 252, currency: 'eur', proration_date: Math.floor(Date.now() / 1000), charge_starts_at: null } } }),
    );
    await page.goto(`/dashboard/store/plans?business=${bakery}`);
    await expect(page.getByTestId('plan-starter').getByTestId('plan-current')).toBeVisible();
    await page.getByTestId('plan-standard').getByTestId('plan-change').click();
    const dialog = page.getByTestId('proration-modal');
    await atEverySize(
      page,
      'BILLING-G17',
      async () => {
        await expect(dialog.getByTestId('proration-row').first()).toBeVisible();
        await dialogInPlace(page, 'proration-modal-submit');
        expect(await cutAmounts(dialog)).toEqual([]);
      },
      false,
    );
    expect(errors).toEqual([]);
  });
});
