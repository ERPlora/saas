// Part 2 of billing: the paid apps in the Store and the pages of Billing, at the
// three sizes (390×844, 834×1112, 1440×900), against the panel's own Django and the rows of
// billing_apps_seed.py. As store.spec.ts, Stripe does not run here: the operations that call it
// (`billing.checkout.start` and `.confirm`, `billing.module.cancel`) are played at the API's edge, and Stripe.js
// is the double of fixtures.ts (`playStripe`); everything else is the real server. Each test names its flow by its
// registry key (BILLING-Gnn); in billing/WORKBOOK.md: G61=F31, G62=F32, G63=F09, G66=F33, G67=F34, G68=F35,
// G05=F36, G92=F22, G94=F23, G95=F08, G17=F11.
// flow: BILLING-F33 BILLING-F34 BILLING-F35 — what the Hub then receives: billing/tests/test_module_end_reaches_the_hub.py.
import type { Locator, Page } from '@playwright/test';

import { addAppInCheckout, businessIdOf, captureAtEverySize, dialogInPlace, expect, gotoWithCharge, panelAccount, payInStripe, qaAccount, seededAndSignedInWarm, test, toast, watchPageErrors } from './fixtures';

seededAndSignedInWarm('billing_apps_seed.py', qaAccount('BILLING_APPS', panelAccount('billing-apps')));
const atEverySize = captureAtEverySize('APP-BILLING-2');

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

/** The charge's summary in its dialog at a size: its rows shown, the dialog in place and no amount cut off (G62, G17). */
const chargeInPlace = (page: Page, dialog: Locator) => async () => {
  await expect(dialog.getByTestId('proration-row').first()).toBeVisible();
  await dialogInPlace(page, 'proration-modal-submit');
  expect(await cutAmounts(dialog)).toEqual([]);
};

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
    await gotoWithCharge(page, `/dashboard/store/modules?business=${bakery}`, 435, 76);
    const confirmed: unknown[] = [];
    await page.route('**/api/billing/checkout/confirm', async (route) => {
      confirmed.push(route.request().postDataJSON());
      await route.fulfill({ json: subscriptionOut(bakery, [{ slug: 'e2e_apps_bookings', valid_until: null }, { slug: 'e2e_apps_loyalty', valid_until: null }]) });
    });
    const loyalty = page.getByTestId('module-e2e_apps_loyalty');
    await loyalty.getByTestId('module-add').click();
    const dialog = page.getByTestId('proration-modal');
    await atEverySize(
      page,
      'BILLING-G62',
      chargeInPlace(page, dialog),
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
    const cafe = await businessIdOf(page.request, 'Café Central');
    const started = await addAppInCheckout(page, cafe, 'e2e_apps_bookings');
    await expect(page.getByTestId('checkout-modal').getByTestId('stripe-double')).toBeVisible();
    expect(started).toEqual([expect.objectContaining({ hub_id: cafe, module: 'e2e_apps_bookings' })]);
    await payInStripe(page);
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
    // The card of the cancelled app: until when the business has it, and «Keep» while it lasts (the sheet gone first:
    // below 640px it slides down, and a capture taken meanwhile shows it halfway).
    await expect(dialog).toBeHidden();
    await atEverySize(page, 'BILLING-G66-keep', async () => {
      await expect(bookings.getByTestId('module-cancelled')).toContainText('(cancelled)');
      await expect(bookings.getByTestId('module-keep')).toBeVisible();
    });
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
    // The invoice and its credit note as Invoices lists them, by the number each page shows.
    const listed = await page.request.get('/api/billing/invoices?limit=50');
    expect(listed.status(), 'GET /api/billing/invoices').toBe(200);
    const byNumber = new Map(((await listed.json()) as { rows: Array<{ id: string; number: string | null }> }).rows.map((row) => [row.number, row.id]));
    const [id, creditId] = ['ERP-2026-90201', 'ERPR-2026-90007'].map((number) => byNumber.get(number));
    expect([id, creditId], 'ERP-2026-90201 and ERPR-2026-90007 in Invoices').toEqual([expect.any(String), expect.any(String)]);
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
      // The apps each plan turns on at once, from the plan's `max_apps` (hubs/0021), worded as /pricing/ (saas#121).
      await expect(page.getByTestId('plan-free').getByTestId('plan-apps')).toHaveText('Up to 20 apps turned on at once');
      await expect(page.getByTestId('plan-starter').getByTestId('plan-apps')).toHaveText('Up to 40 apps turned on at once');
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G17: a paying business changes plan with what it is charged today', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await gotoWithCharge(page, `/dashboard/store/plans?business=${bakery}`, 1452, 252);
    await expect(page.getByTestId('plan-starter').getByTestId('plan-current')).toBeVisible();
    await page.getByTestId('plan-standard').getByTestId('plan-change').click();
    const dialog = page.getByTestId('proration-modal');
    await atEverySize(
      page,
      'BILLING-G17',
      chargeInPlace(page, dialog),
      false,
    );
    expect(errors).toEqual([]);
  });
});
