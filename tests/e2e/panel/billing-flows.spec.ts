// The flows of «the plan and its money» (billing/WORKBOOK.md, MIGRATION-TASK APP-BILLING-1) on their screens, at
// the three sizes of the migration (390×844, 834×1112, 1440×900), against the panel's own Django and the rows of
// billing_seed.py. As billing.spec.ts and store.spec.ts, Stripe does not run here: the operations that call it
// (`billing.plan.cancel`, `.keep`, `billing.checkout.start`, `billing.portal.open`) are played at the API's edge;
// everything else is the real server. Each test names its flow in its title.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { businessIdOf, djangoPrint, expect, panelAccount, qaAccount, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const BILLING = qaAccount('BILLING', panelAccount('billing'));
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

function seedBilling(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/billing_seed.py', action], { cwd: SAAS_DIR, env: djangoEnv(true), stdio: 'pipe' });
}

test.beforeEach(async ({ page }) => {
  seedBilling('seed');
  await signIn(page.request, BILLING);
});
test.afterAll(() => seedBilling('clear'));

const toast = (page: Page, text: string | RegExp) => page.locator('ion-toast').filter({ hasText: text });

/** `ready` at each size: no sideways scroll, a capture `APP-BILLING-1-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-BILLING-1-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.describe('billing flows', () => {
  test('BILLING-G82: «Payment details» says who ERPlora invoices for the businesses, and edits it', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/billing/payment');
    await atEverySize(page, 'BILLING-G82', async () => {
      await expect(page.getByTestId('profile-name').first()).toBeVisible();
      await expect(page.getByTestId('profile-edit').first()).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G84: the Plan card of a business leads to the Store, «Upgrade plan» on Free and «Change plan» paying', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.goto(`/businesses/${cafe}/summary`);
    const store = page.getByTestId('summary-plan-store');
    await atEverySize(page, 'BILLING-G84', async () => {
      await expect(page.getByTestId('summary-plan')).toBeVisible();
      await expect(store).toHaveText('Upgrade plan');
    });
    await store.click();
    await expect(page).toHaveURL(new RegExp(`/store/plans\\?business=${cafe}$`));
    await page.goto(`/businesses/${bakery}/summary`);
    await expect(page.getByTestId('summary-plan-store')).toHaveText('Change plan');
    expect(errors).toEqual([]);
  });

  test('BILLING-G87: a business on Free sees «Upgrade» on every paid plan of the Store', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.goto(`/store/plans?business=${cafe}`);
    await atEverySize(page, 'BILLING-G87', async () => {
      await expect(page.getByTestId('plan-starter').getByTestId('plan-upgrade')).toBeVisible();
      await expect(page.getByTestId('plan-standard').getByTestId('plan-upgrade')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G88: a paying business sees its plan as current and changes to another with its proration', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.route('**/api/billing/checkout/start', (route) =>
      route.fulfill({
        json: { flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: { amount_due_cents: 1452, tax_cents: 252, currency: 'eur', proration_date: Math.floor(Date.now() / 1000), charge_starts_at: null } },
      }),
    );
    await page.goto(`/store/plans?business=${bakery}`);
    await atEverySize(page, 'BILLING-G88', async () => {
      await expect(page.getByTestId('plan-starter').getByTestId('plan-current')).toBeVisible();
      await expect(page.getByTestId('plan-standard').getByTestId('plan-change')).toBeVisible();
    });
    await page.getByTestId('plan-standard').getByTestId('plan-change').click();
    const dialog = page.getByTestId('proration-modal');
    await expect(dialog.getByTestId('proration-row').first()).toBeVisible();
    await page.screenshot({ path: shot('APP-BILLING-1-BILLING-G88-proration-1440') });
    expect(errors).toEqual([]);
  });

  test('BILLING-G55 and BILLING-G56: «Cancel plan» ends it with its period, and «Keep the plan» undoes it', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    const asked: string[] = [];
    const answer = (cancelAtPeriodEnd: boolean) => ({
      hub_id: bakery, plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: cancelAtPeriodEnd,
      current_period_end: new Date(Date.now() + 20 * 86_400_000).toISOString(), trial_end: null, modules: [],
    });
    await page.route('**/api/billing/plan/cancel', async (route) => {
      asked.push('cancel');
      await route.fulfill({ json: answer(true) });
    });
    await page.route('**/api/billing/plan/keep', async (route) => {
      asked.push('keep');
      await route.fulfill({ json: answer(false) });
    });
    await page.goto('/billing/subscriptions');
    const row = page.locator(`[data-testid="subscriptions-row"][data-id="${bakery}"]`);
    await atEverySize(page, 'BILLING-G55', async () => {
      await expect(row).toBeVisible();
    });
    await page.getByTestId(`subscriptions-row-${bakery}-menu`).click();
    await page.getByTestId(`subscriptions-row-${bakery}-cancel_plan`).click();
    const dialog = page.getByTestId('cancel-plan');
    await expect(dialog).toContainText('Panadería López · Starter');
    await page.screenshot({ path: shot('APP-BILLING-1-BILLING-G55-dialog-1440') });
    await page.getByTestId('cancel-plan-submit').click();
    await expect(toast(page, /Panadería López/)).toBeVisible();
    await expect(dialog).toBeHidden();
    expect(asked).toEqual(['cancel']);
    // «Keep the plan» is what the server offers once the plan ends with its period (the seed marks it so).
    djangoPrint(`from hubs.models import Subscription;print(Subscription.objects.filter(hub_id='${bakery}').update(cancel_at_period_end=True))`);
    await page.goto('/billing/subscriptions');
    await atEverySize(page, 'BILLING-G56', async () => {
      await expect(row.getByTestId(`subscriptions-row-${bakery}-lead`)).toHaveText('Keep the plan');
    });
    await row.getByTestId(`subscriptions-row-${bakery}-lead`).click();
    await expect.poll(() => asked).toEqual(['cancel', 'keep']);
    expect(errors).toEqual([]);
  });

  // Paying it (the invoice page at Stripe, «Invoice paid» back) is billing.spec.ts's «Pay» test.
  test('BILLING-G54 and BILLING-G58: an unpaid plan is said on Invoices business by business, with its way to pay', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/billing/invoices');
    const declined = page.getByTestId('unpaid-group-item').filter({ hasText: 'Bar La Plaza' });
    const soft = page.getByTestId('unpaid-group-item').filter({ hasText: 'Bar Norte' });
    await atEverySize(page, 'BILLING-G54', async () => {
      // The bank declined the card: change it first, «Pay» waits.
      await expect(declined.getByTestId('unpaid-group-change-card')).toBeVisible();
      await expect(declined.getByTestId('pay-invoice').locator('button')).toBeDisabled();
    });
    await atEverySize(page, 'BILLING-G58', async () => {
      // A soft failure: «Pay» pays it again, and the business works again.
      await expect(soft.getByTestId('pay-invoice').locator('button')).toBeEnabled();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G69: «Invoices» lists the invoices of every business it pays', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/billing/invoices');
    await atEverySize(page, 'BILLING-G69', async () => {
      await expect(page.getByTestId('invoices-row').first()).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G70: «Subscriptions» has one row per business with what it pays', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/billing/subscriptions');
    await atEverySize(page, 'BILLING-G70', async () => {
      await expect(page.getByTestId('subscriptions-row')).toHaveCount(3);
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G71: «Change card» opens the Stripe portal of that payer', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.route(/^https:\/\/billing\.stripe\.com\//, (route) =>
      route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Stripe (test double)</title><p>Stripe (test double)</p>' }),
    );
    const opened: unknown[] = [];
    await page.route('**/api/billing/portal', async (route) => {
      opened.push(route.request().postDataJSON());
      await route.fulfill({ json: { url: 'https://billing.stripe.com/p/session/e2e' } });
    });
    await page.goto('/billing/invoices');
    const change = page.getByTestId('unpaid-group-item').filter({ hasText: 'Bar La Plaza' }).getByTestId('unpaid-group-change-card');
    await atEverySize(page, 'BILLING-G71', async () => {
      await expect(change).toBeVisible();
    });
    await change.click();
    await page.waitForURL('https://billing.stripe.com/p/session/e2e');
    expect(opened).toEqual([{ hub_id: await businessIdOf(page.request, 'Bar La Plaza') }]);
    expect(errors).toEqual([]);
  });
});
