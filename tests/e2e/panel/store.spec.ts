// The Store (`/store/:tab`, plan 2026-10-13 L2-D; mockups `store.html`) in Chrome, against the panel's own
// Django (project.ts) and the rows of store_seed.py. Stripe cannot run here: no keys, no network to it. The
// spec plays Stripe at the browser's boundary — a `Stripe` global that records the publishable key and the
// client secret and mounts a placeholder where the Embedded Checkout would be, and the answers of the
// operations that call Stripe (`billing.checkout.start` and `.confirm`, `billing.module.keep`) — so it
// proves the page up to the `client_secret` request and the modal's mount, not Stripe's own form, the
// webhook nor a real charge (`store-checkout.spec.ts` with `stripe listen` does, «Hecho L2»).
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import type { Page, Request } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { businessIdOf, expect, panelAccount, signIn, test, VIEWPORTS, watchPageErrors } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SHOTS_DIR = process.env.SHOTS_DIR ?? '/tmp/l2d-shots';
mkdirSync(SHOTS_DIR, { recursive: true });

function seedStore(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/store_seed.py', action], {
    cwd: SAAS_DIR,
    env: { ...process.env, DEBUG: 'True' },
    stdio: 'pipe',
  });
}

test.beforeAll(() => seedStore('seed'));
test.afterAll(() => seedStore('clear'));

const STORE = panelAccount('store');

/** Stripe.js as the page would get it from js.stripe.com: records what the page hands it. */
async function playStripe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    type Options = { fetchClientSecret: () => Promise<string>; onComplete?: () => void };
    const w = window as unknown as Record<string, unknown> & { __stripe: { keys: string[]; secrets: string[]; mountedIn: string[]; destroyed: number; complete?: () => void } };
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

const stripeState = (page: Page) =>
  page.evaluate(() => {
    const s = (window as unknown as { __stripe: { keys: string[]; secrets: string[]; mountedIn: string[]; destroyed: number } }).__stripe;
    return { keys: s.keys, secrets: s.secrets, mountedIn: s.mountedIn, destroyed: s.destroyed };
  });

const toast = (page: Page, text: string | RegExp) => page.locator('ion-toast').filter({ hasText: text });

/** Every request the page makes to Stripe's origins (none is expected: the double plays Stripe.js). */
function watchStripeRequests(page: Page): string[] {
  const seen: string[] = [];
  page.on('request', (request: Request) => {
    if (/stripe\.com/.test(request.url())) seen.push(request.url());
  });
  return seen;
}

/** The sideways scroll of the page on screen, read where Ionic scrolls (as viewports.spec.ts). */
async function sidewaysScroll(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');
    return scroll && scroll.scrollWidth > scroll.clientWidth + 1 ? [`ion-content ${scroll.scrollWidth} > ${scroll.clientWidth}`] : [];
  });
}

async function settled(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running' || animation.effect?.getTiming().iterations === Infinity),
  );
}

test.describe('store', () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page.request, STORE);
  });

  test('the SPA admits Stripe in its CSP, and nothing loads from Stripe until a payment opens', async ({ page }) => {
    const stripe = watchStripeRequests(page);
    const response = await page.goto('/store/plans');
    const csp = response?.headers()['content-security-policy'] ?? '';
    expect(csp).toMatch(/script-src [^;]*https:\/\/js\.stripe\.com/);
    expect(csp).toMatch(/frame-src 'self'[^;]*https:\/\/checkout\.stripe\.com/);
    expect(csp).toMatch(/connect-src [^;]*https:\/\/api\.stripe\.com/);
    await expect(page.getByTestId('store-plans')).toBeVisible();
    expect(stripe).toEqual([]);
  });

  test('it sells to the business it came from; on Free, «Upgrade» opens the Embedded Checkout from the client_secret', async ({ page }) => {
    const errors = watchPageErrors(page);
    await playStripe(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const started: unknown[] = [];
    await page.route('**/api/billing/checkout/start', async (route) => {
      started.push(route.request().postDataJSON());
      await route.fulfill({ json: { flow: 'checkout', session_id: 'cs_test_e2e', client_secret: 'cs_test_e2e_secret', publishable_key: 'pk_test_e2e', preview: null } });
    });
    await page.goto(`/store/plans?business=${cafe}`);
    await expect(page.getByTestId('store-business')).toHaveJSProperty('value', cafe);
    await expect(page.getByTestId('plan-free').getByTestId('plan-current')).toBeVisible();
    await page.getByTestId('store-period-year').click();
    await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
    const dialog = page.getByTestId('checkout-modal');
    await expect(dialog.getByTestId('checkout-for')).toHaveText('For Café Central · renews every year');
    await expect(dialog.getByTestId('checkout-invoice-to')).toContainText('Café Central SL');
    await expect(dialog.getByTestId('stripe-double')).toBeVisible();
    expect(started).toEqual([{ hub_id: cafe, plan: 'starter', interval: 'year', promo_code: '' }]);
    expect(await stripeState(page)).toMatchObject({ keys: ['pk_test_e2e'], secrets: ['cs_test_e2e_secret'], mountedIn: ['checkout-stripe'] });
    await page.screenshot({ path: join(SHOTS_DIR, 'store-checkout-1440.png') });
    // Stripe says the payment went through: the page goes to the business and says so.
    await page.evaluate(() => (window as unknown as { __stripe: { complete: () => void } }).__stripe.complete());
    await expect(page).toHaveURL(new RegExp(`/businesses/${cafe}/summary$`));
    await expect(toast(page, 'Café Central is now on Starter')).toBeVisible();
    expect((await stripeState(page)).destroyed).toBe(1);
    expect(errors).toEqual([]);
  });

  test('a paying business adds a module in its own dialog, with its proration, and then it is «Activating…»', async ({ page }) => {
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.route('**/api/billing/checkout/start', (route) =>
      route.fulfill({ json: { flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: { amount_due_cents: 653, tax_cents: 113, currency: 'eur', proration_date: Math.floor(Date.now() / 1000), charge_starts_at: null } } }),
    );
    const confirmed: unknown[] = [];
    await page.route('**/api/billing/checkout/confirm', async (route) => {
      confirmed.push(route.request().postDataJSON());
      await route.fulfill({
        json: { hub_id: bakery, plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: null, trial_end: null, modules: [{ slug: 'e2e_bookings', source: 'purchase', valid_until: null }] },
      });
    });
    await page.goto(`/store/modules?business=${bakery}`);
    const bookings = page.getByTestId('module-e2e_bookings');
    await expect(bookings.getByTestId('module-name')).toHaveText('E2E Bookings');
    await expect(page.getByTestId('module-e2e_free_app')).toHaveCount(0);
    await page.screenshot({ path: join(SHOTS_DIR, 'store-modules-1440.png'), fullPage: true });
    await bookings.getByTestId('module-add').click();
    const dialog = page.getByTestId('proration-modal');
    await expect(dialog.getByTestId('proration-row')).toHaveText([/Today \(prorated\)\s*€5\.40 \+ VAT/, /VAT\s*€1\.13/, /Total today\s*€6\.53/, /€9\.00\/month \+ VAT/]);
    await page.screenshot({ path: join(SHOTS_DIR, 'store-proration-1440.png') });
    await dialog.getByTestId('proration-modal-submit').click();
    await expect(toast(page, 'E2E Bookings added to Panadería López: it turns on in a few seconds')).toBeVisible();
    await expect(bookings.getByTestId('module-activating')).toHaveText(/Activating… in Panadería López/);
    await expect(bookings.getByTestId('module-add')).toHaveCount(0);
    expect(confirmed).toEqual([expect.objectContaining({ hub_id: bakery, module: 'e2e_bookings' })]);
  });

  test('a cancelled module is kept with «Keep · no charge today»', async ({ page }) => {
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.route('**/api/billing/module/keep', (route) =>
      route.fulfill({ json: { hub_id: bakery, plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: null, trial_end: null, modules: [{ slug: 'e2e_loyalty', source: 'purchase', valid_until: null }] } }),
    );
    await page.goto(`/store/modules?business=${bakery}`);
    const loyalty = page.getByTestId('module-e2e_loyalty');
    await expect(loyalty.getByTestId('module-cancelled')).toContainText('(cancelled)');
    await loyalty.getByTestId('module-keep').click();
    await expect(toast(page, 'E2E Loyalty is kept')).toBeVisible();
    await expect(loyalty.getByTestId('module-owned')).toBeVisible();
  });

  test('a business with an unpaid invoice buys nothing, and says why', async ({ page }) => {
    const bar = await businessIdOf(page.request, 'Bar La Plaza');
    await page.goto(`/store/plans?business=${bar}`);
    await expect(page.getByTestId('store-unpaid')).toContainText('Bar La Plaza has an unpaid invoice');
    await expect(page.getByTestId('store-unpaid')).toContainText('The bank declined the last card.');
    await page.getByTestId('store-period-year').click();
    // ion-button's own native button (in its shadow) is what the browser disables.
    await expect(page.getByTestId('plan-switch').locator('button')).toBeDisabled();
    await expect(page.getByTestId('plan-starter').getByTestId('plan-hint')).toHaveText('Pay the pending invoice first.');
    await page.screenshot({ path: join(SHOTS_DIR, 'store-unpaid-1440.png'), fullPage: true });
  });

  test('inside the apps and on the account surface it does not sell: no prices, no Stripe, no link out', async ({ page }) => {
    const stripe = watchStripeRequests(page);
    await page.goto('/store/plans?surface=account');
    const notice = page.getByTestId('store-in-app');
    // Already in the browser: why nothing is bought here, not «go to erplora.com in your browser» (audit 2 S-09).
    await expect(notice).toContainText('Nothing is bought from here');
    await expect(notice).toContainText('This account was opened from the app, and the app does not sell');
    await expect(page.getByTestId('plan-starter')).toHaveCount(0);
    expect(await page.locator('ion-router-outlet').innerText()).not.toMatch(/€/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: join(SHOTS_DIR, 'store-app-390.png') });
    // Back to the web for the rest of the session.
    await page.goto('/store/plans?surface=web');
    await expect(page.getByTestId('store-plans')).toBeVisible();
    // The Tauri bridge (the installed apps).
    await page.addInitScript(() => {
      (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    });
    await page.goto('/store/modules');
    await expect(page.getByTestId('store-in-app')).toBeVisible();
    await expect(page.getByTestId('module-e2e_bookings')).toHaveCount(0);
    expect(stripe).toEqual([]);
  });

  for (const { width, height } of VIEWPORTS) {
    for (const theme of ['light', 'dark'] as const) {
      test(`Plans and Modules at ${width} px (${theme}): no sideways scroll, no error`, async ({ page }) => {
        const errors = watchPageErrors(page);
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height });
        const bakery = await businessIdOf(page.request, 'Panadería López');
        for (const tab of ['plans', 'modules'] as const) {
          await page.goto(`/store/${tab}?business=${bakery}`);
          await expect(page.getByTestId(`store-${tab}`)).toBeVisible();
          await settled(page);
          expect(await sidewaysScroll(page), `${tab} at ${width}`).toEqual([]);
          await page.screenshot({ path: join(SHOTS_DIR, `store-${tab}-${width}-${theme}.png`), fullPage: true });
        }
        expect(errors).toEqual([]);
      });
    }
  }
});
