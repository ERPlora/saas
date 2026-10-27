// Part 3 of billing (MIGRATION-TASK APP-BILLING-3): the screens of the old SaaS's pricing, payment result, retry,
// billing details, portal and app purchase, which part 3 joins to the flows parts 1 and 2 built, at the three sizes
// of the migration (390×844, 834×1112, 1440×900), against the panel's own Django and the rows of
// billing_apps_seed.py. As billing-apps.spec.ts, Stripe does not run here: the operations that call it
// (`billing.checkout.start` and `.confirm`, `billing.portal.open`, `billing.payment_method.get`) are played at the
// API's edge, and Stripe.js is a double that mounts a placeholder; everything else (the billing details saved
// included) is the real server. Each test names its flow by its registry key (BILLING-Gnn); in
// billing/WORKBOOK.md: G19=F08, G20=F09, G21=F10, G26=F01, G27=F24, G28=F32.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { businessIdOf, expect, panelAccount, qaAccount, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

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

/** `ready` at each size: no sideways scroll, a capture `APP-BILLING-3-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>, fullPage = true): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-BILLING-3-${key}-${size.name}`), fullPage });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** A dialog that slides in again at a new size is in place once its button `testid` is whole on screen and still. */
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

const CHECKOUT = { flow: 'checkout', session_id: 'cs_test_e2e_support', client_secret: 'cs_test_e2e_support_secret', publishable_key: 'pk_test_e2e', preview: null };

test.describe('billing part 3: the screens of the old pricing, payment, billing details and purchase', () => {
  test('BILLING-G19: the plans of the Store, with their monthly and their annual price', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    const starter = page.getByTestId('plan-starter');
    await expect(starter.getByTestId('plan-upgrade')).toBeVisible();
    const monthly = (await starter.getByTestId('plan-price').innerText()).trim();
    await page.getByTestId('store-period-year').click();
    await expect(starter.getByTestId('plan-price')).not.toHaveText(monthly);
    await atEverySize(page, 'BILLING-G19', async () => {
      await expect(page.getByTestId('plan-free').getByTestId('plan-current')).toBeVisible();
      await expect(starter.getByTestId('plan-price')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G20: back from paying a plan, the business says it is on it', async ({ page }) => {
    const errors = watchPageErrors(page);
    await playStripe(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.route('**/api/billing/checkout/start', (route) => route.fulfill({ json: CHECKOUT }));
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
    await expect(page.getByTestId('checkout-modal').getByTestId('stripe-double')).toBeVisible();
    await page.evaluate(() => (window as unknown as { __stripe: { complete: () => void } }).__stripe.complete());
    await expect(page).toHaveURL(new RegExp(`/dashboard/businesses/${cafe}/summary$`));
    await expect(toast(page, 'Café Central is now on Starter')).toBeVisible();
    await atEverySize(page, 'BILLING-G20', async () => {
      await expect(page.getByTestId('summary-plan')).toBeVisible();
    });
    expect(errors).toEqual([]);
  });

  test('BILLING-G21: a payment closed before paying opens again with the same choice', async ({ page }) => {
    const errors = watchPageErrors(page);
    await playStripe(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const started: unknown[] = [];
    await page.route('**/api/billing/checkout/start', async (route) => {
      started.push(route.request().postDataJSON());
      await route.fulfill({ json: CHECKOUT });
    });
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    const upgrade = page.getByTestId('plan-starter').getByTestId('plan-upgrade');
    const dialog = page.getByTestId('checkout-modal');
    await upgrade.click();
    await expect(dialog.getByTestId('stripe-double')).toBeVisible();
    await page.getByTestId('checkout-modal-close').click();
    await expect(dialog).toBeHidden();
    await upgrade.click();
    await atEverySize(
      page,
      'BILLING-G21',
      async () => {
        await expect(dialog.getByTestId('stripe-double')).toBeVisible();
        await expect(dialog.getByTestId('checkout-for')).toHaveText('For Café Central · renews every month');
      },
      false,
    );
    // The same choice twice: the server answers it with the same payment (billing/tests/test_checkout.py).
    expect(started).toEqual([
      { hub_id: cafe, plan: 'starter', interval: 'month', promo_code: '' },
      { hub_id: cafe, plan: 'starter', interval: 'month', promo_code: '' },
    ]);
    expect(errors).toEqual([]);
  });

  test('BILLING-G26: the billing details are edited and saved, for the next invoices', async ({ page }) => {
    const errors = watchPageErrors(page);
    await page.goto('/dashboard/billing/payment');
    await expect(page.getByTestId('profile-name')).toHaveText('Panadería López S.L.');
    await page.getByTestId('profile-edit').click();
    await atEverySize(
      page,
      'BILLING-G26',
      async () => {
        await dialogInPlace(page, 'billing-profile-submit');
      },
      false,
    );
    await page.getByTestId('details-city').locator('input').fill('Getafe');
    await page.getByTestId('billing-profile-submit').click();
    await expect(toast(page, 'Billing details saved')).toBeVisible();
    await expect(page.getByTestId('billing-profile-submit')).toBeHidden();
    expect(errors).toEqual([]);
  });

  test('BILLING-G27: «Change card» opens Stripe’s page of that payer', async ({ page }) => {
    const errors = watchPageErrors(page);
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.route('**/api/billing/payment-method', (route) =>
      route.fulfill({
        json: {
          methods: [
            {
              businesses: [{ id: bakery, name: 'Panadería López' }],
              card: { brand: 'visa', last4: '4242', exp_month: 8, exp_year: 2028 },
              unavailable: false,
              last_failure: null,
            },
          ],
        },
      }),
    );
    await page.route(/^https:\/\/billing\.stripe\.com\//, (route) =>
      route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Stripe (test double)</title><p>Stripe (test double)</p>' }),
    );
    const opened: unknown[] = [];
    await page.route('**/api/billing/portal', async (route) => {
      opened.push(route.request().postDataJSON());
      await route.fulfill({ json: { url: 'https://billing.stripe.com/p/session/e2e' } });
    });
    await page.goto('/dashboard/billing/payment');
    const change = page.getByTestId('payment-change');
    await atEverySize(page, 'BILLING-G27', async () => {
      await expect(page.getByTestId('payment-card')).toHaveText('Visa •••• 4242');
      await expect(change).toHaveText('Change card');
    });
    await change.click();
    await page.waitForURL('https://billing.stripe.com/p/session/e2e');
    expect(opened).toEqual([{ hub_id: bakery }]);
    expect(errors).toEqual([]);
  });

  test('BILLING-G28: a business on Free buys a paid app in the secure checkout', async ({ page }) => {
    const errors = watchPageErrors(page);
    await playStripe(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const started: unknown[] = [];
    await page.route('**/api/billing/checkout/start', async (route) => {
      started.push(route.request().postDataJSON());
      await route.fulfill({ json: CHECKOUT });
    });
    await page.goto(`/dashboard/store/modules?business=${cafe}`);
    await page.getByTestId('module-e2e_apps_bookings').getByTestId('module-add').click();
    const dialog = page.getByTestId('checkout-modal');
    await atEverySize(
      page,
      'BILLING-G28',
      async () => {
        await expect(dialog.getByTestId('stripe-double')).toBeVisible();
      },
      false,
    );
    expect(started).toEqual([expect.objectContaining({ hub_id: cafe, module: 'e2e_apps_bookings' })]);
    expect(errors).toEqual([]);
  });
});
