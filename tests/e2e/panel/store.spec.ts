// The Store (`/dashboard/store/:tab`) in Chrome, against the panel's own Django (project.ts) and the rows of
// store_seed.py. Stripe cannot run here: no keys, no network to it. The spec plays Stripe at the browser's boundary
// with stripe.ts — its Stripe.js (`playStripe`, which records the publishable key and the client secret and
// mounts a placeholder where the Embedded Checkout would be) and the answers of the operations that call Stripe
// (`answerCheckoutStart`; `billing.checkout.confirm` and `billing.module.keep` here) — so it proves the page up to
// the `client_secret` request and the modal's mount, not Stripe's own form, the webhook nor a real charge
// (`store-checkout.spec.ts` with `stripe listen` does).
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import type { Page, Request } from '@playwright/test';

import { overflowingBoxes } from '../horizontal-overflow';
import { panelAccount, qaAccount } from './accounts';
import { businessIdOf } from './businesses';
import { djangoPrint, runSeed } from './django';
import { expect, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { repeatedTop, settled, shot, stripedAfterResize, toast, VIEWPORTS } from './screen';
import { signIn } from './session';
import { answerCheckoutStart, gotoWithCharge, gotoWithCheckout, payInStripe, playStripe, stripeState } from './stripe';

const SHOTS_DIR = process.env.SHOTS_DIR ?? '/tmp/l2d-shots';
mkdirSync(SHOTS_DIR, { recursive: true });

test.beforeAll(() => runSeed('store_seed.py', 'seed'));
test.afterAll(() => runSeed('store_seed.py', 'clear'));

const STORE = qaAccount('STORE', panelAccount('store'));

/** Every request the page makes to Stripe's origins (none is expected: the double plays Stripe.js). */
function watchStripeRequests(page: Page): string[] {
  const seen: string[] = [];
  page.on('request', (request: Request) => {
    if (/stripe\.com/.test(request.url())) seen.push(request.url());
  });
  return seen;
}

/** Leaves the seeded business `name` on the plan `slug`, as a paid purchase would (nothing reaches Stripe nor the Hub). */
function putOnPlan(name: string, slug: string, cancelling = false): void {
  djangoPrint(
    [
      'from hubs.models import Plan, Subscription',
      `Subscription.objects.filter(hub__name="${name}", hub__slug__startswith="e2e-store-").update(plan=Plan.objects.get(slug="${slug}"), cancel_at_period_end=${cancelling ? 'True' : 'False'})`,
    ].join('\n'),
  );
}

/** Takes the Stripe prices off the plan `slug`, as a plan the admin has not priced yet; the call it returns puts them back. */
function withoutStripePrices(slug: string): () => void {
  const saved = djangoPrint(
    [
      'import json',
      'from hubs.models import Plan',
      `plan = Plan.objects.get(slug="${slug}")`,
      'print(json.dumps([plan.stripe_price_id, plan.stripe_price_id_annual]))',
      'Plan.objects.filter(pk=plan.pk).update(stripe_price_id="", stripe_price_id_annual="")',
    ].join('\n'),
  );
  const [month, year] = JSON.parse(saved) as [string, string];
  return () => {
    djangoPrint(
      [
        'from hubs.models import Plan',
        `Plan.objects.filter(slug="${slug}").update(stripe_price_id=${JSON.stringify(month)}, stripe_price_id_annual=${JSON.stringify(year)})`,
      ].join('\n'),
    );
  };
}

/** The sideways scroll of the page on screen, read where Ionic scrolls (the one measure, `overflowingBoxes`). */
async function sidewaysScroll(page: Page): Promise<string[]> {
  return overflowingBoxes(page, 1);
}

async function checkPayingPlans(page: Page, businessId: string, width: number): Promise<void> {
  await page.goto(`/dashboard/store/plans?business=${businessId}`);
  await expect(page.getByTestId('store-plans')).toBeVisible();
  await expect(page.locator('.plans-grid > ion-card')).toHaveCount(6);
  await expect(page.getByTestId('plan-free').getByTestId('plan-downgrade')).toBeVisible();
  await expect(page.getByTestId('plan-standard').getByTestId('plan-change')).toBeVisible();
  await settled(page);
  expect(await sidewaysScroll(page), `paying plans at ${width}`).toEqual([]);
}

/** Ionic scrolls inside the viewport: enlarge that viewport to capture the whole plan page, then restore its size. */
async function planShot(page: Page, name: string): Promise<void> {
  const viewport = page.viewportSize();
  if (!viewport) throw new Error('The plan screenshot needs a viewport');
  const fullHeight = await page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1);
    const content = shown?.querySelector('ion-content');
    const scroller = content?.shadowRoot?.querySelector<HTMLElement>('[part="scroll"]');
    if (!content || !scroller) return window.innerHeight;
    scroller.scrollTop = 0;
    const box = content.getBoundingClientRect();
    return Math.ceil(scroller.scrollHeight + box.top + window.innerHeight - box.bottom);
  });
  await page.setViewportSize({ width: viewport.width, height: Math.max(viewport.height, fullHeight) });
  await settled(page);
  await page.screenshot({ path: join(SHOTS_DIR, name), fullPage: true });
  await page.setViewportSize(viewport);
  await settled(page);
}

test.describe('store', () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page.request, STORE);
  });

  test('the SPA admits Stripe in its CSP, and nothing loads from Stripe until a payment opens', async ({ page }) => {
    const stripe = watchStripeRequests(page);
    const response = await page.goto('/dashboard/store/plans');
    const csp = response?.headers()['content-security-policy'] ?? '';
    expect(csp).toMatch(/script-src [^;]*https:\/\/js\.stripe\.com/);
    expect(csp).toMatch(/frame-src 'self'[^;]*https:\/\/checkout\.stripe\.com/);
    expect(csp).toMatch(/connect-src [^;]*https:\/\/api\.stripe\.com/);
    await expect(page.getByTestId('store-plans')).toBeVisible();
    expect(stripe).toEqual([]);
  });

  test('it sells to the business it came from; on Free, «Upgrade» opens the Embedded Checkout from the client_secret', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const started = await gotoWithCheckout(page, `/dashboard/store/plans?business=${cafe}`);
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
    await payInStripe(page);
    await expect(page).toHaveURL(new RegExp(`/dashboard/businesses/${cafe}/summary$`));
    await expect(toast(page, 'Café Central is now on Starter')).toBeVisible();
    expect((await stripeState(page)).destroyed).toBe(1);
    expect(errors).toEqual([]);
  });

  // saas#344 (BILLING-F09): the notice of what was paid for sits above the business's section tabbar, as every notice
  // of the panel does, at the three sizes. It is asked while the payment dialog closes over the business's page:
  // where it goes is the bar of the screen on view when it shows, not of the one under the dialog.
  test('back from paying a plan, its notice sits above the business’s section tabbar, never over it (saas#344)', async ({ page }) => {
    const errors = watchPageErrors(page);
    await playStripe(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    await answerCheckoutStart(page);
    const notice = toast(page, 'Café Central is now on Starter');
    const tabbar = page.locator('ion-footer.section-tabbar').filter({ has: page.getByTestId('tab-summary') });
    for (const size of [{ width: 375, height: 667 }, { width: 820, height: 1180 }, { width: 1440, height: 900 }]) {
      await page.setViewportSize(size);
      await page.goto(`/dashboard/store/plans?business=${cafe}`);
      await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
      await expect(page.getByTestId('checkout-modal').getByTestId('stripe-double')).toBeVisible();
      await payInStripe(page);
      await expect(page).toHaveURL(new RegExp(`/dashboard/businesses/${cafe}/summary$`));
      await expect(notice).toBeVisible();
      await settled(page);
      await page.screenshot({ path: shot(`STORE-paid-notice-${size.width}`) });
      // Soft: every size is measured (and captured) even when one fails.
      await expect.soft(notice, `the notice whole on screen at ${size.width}`).toBeInViewport({ ratio: 1 });
      const [bar, box] = [await tabbar.boundingBox(), await notice.boundingBox()];
      expect.soft(bar && box && box.y + box.height <= bar.y, `the notice's bottom above the tabbar's top at ${size.width}: ${JSON.stringify({ bar, box })}`).toBe(true);
    }
    expect(errors).toEqual([]);
  });

  // saas#434 (BILLING-F07, F08, F27): the internal plan is offered only to the business ERPlora's staff marked in the
  // admin, and it is bought like any plan; the catalog of every other business leaves it out.
  test('only the business ERPlora marked is offered «Payment Test», and it pays it like any plan (saas#434)', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const marked = await businessIdOf(page.request, 'Prueba ERPlora');
    const started = await gotoWithCheckout(page, `/dashboard/store/plans?business=${cafe}`);
    await expect(page.getByTestId('plan-free').getByTestId('plan-current')).toBeVisible();
    await expect(page.getByTestId('plan-payment-test')).toHaveCount(0);
    await page.goto(`/dashboard/store/plans?business=${marked}`);
    const internal = page.getByTestId('plan-payment-test');
    await expect(internal.getByTestId('plan-name')).toHaveText('Payment Test (internal)');
    await internal.getByTestId('plan-upgrade').click();
    await expect(page.getByTestId('checkout-modal').getByTestId('stripe-double')).toBeVisible();
    expect(started).toEqual([{ hub_id: marked, plan: 'payment-test', interval: 'month', promo_code: '' }]);
    expect(errors).toEqual([]);
  });

  // saas#436 (HUBS-F21): the page of a business on the internal plan said «—» in what the plan covers, for it looked
  // the plan up among the plans on sale, which leave the internal ones out.
  test('a business on «Payment Test» reads on its page what that plan covers (saas#436)', async ({ page }) => {
    const errors = watchPageErrors(page);
    const marked = await businessIdOf(page.request, 'Prueba ERPlora');
    putOnPlan('Prueba ERPlora', 'payment-test');
    try {
      for (const size of [{ width: 375, height: 667 }, { width: 820, height: 1180 }, { width: 1440, height: 900 }]) {
        await page.setViewportSize(size);
        await page.goto(`/dashboard/businesses/${marked}/summary`);
        await expect(page.getByTestId('summary-plan').locator('.card-title')).toHaveText('Payment Test (internal)');
        await expect(page.getByTestId('summary-plan-devices').locator('dd')).toHaveText('Unlimited');
        await expect(page.getByTestId('summary-plan-apps').locator('dd')).toHaveText('40');
        await expect(page.getByTestId('summary-plan-store')).toHaveText('Change plan');
        await settled(page);
        await page.screenshot({ path: shot(`STORE-internal-plan-summary-${size.width}`) });
      }
    } finally {
      putOnPlan('Prueba ERPlora', 'free');
    }
    expect(errors).toEqual([]);
  });

  test('Stripe.js that cannot load is said in the dialog, with «Retry»: waiting for its place hides no real failure (saas#326)', async ({ page }) => {
    await page.route(/^https:\/\/js\.stripe\.com\//, (route) => route.abort());
    const cafe = await businessIdOf(page.request, 'Café Central');
    await answerCheckoutStart(page);
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    await expect(page.getByTestId('plan-free').getByTestId('plan-current')).toBeVisible();
    await page.getByTestId('plan-starter').getByTestId('plan-upgrade').click();
    const dialog = page.getByTestId('checkout-modal');
    await expect(dialog.getByTestId('checkout-error')).toContainText('We could not open the secure payment');
    await expect(dialog.getByTestId('checkout-retry')).toBeVisible();
    await expect(dialog.getByTestId('checkout-stripe')).toBeHidden();
  });

  test('a paying business adds a module in its own dialog, with its proration, and then it is «Activating…»', async ({ page }) => {
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await gotoWithCharge(page, `/dashboard/store/modules?business=${bakery}`, 653, 113);
    const confirmed: unknown[] = [];
    await page.route('**/api/billing/checkout/confirm', async (route) => {
      confirmed.push(route.request().postDataJSON());
      await route.fulfill({
        json: { hub_id: bakery, plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: null, trial_end: null, modules: [{ slug: 'e2e_bookings', source: 'purchase', valid_until: null }] },
      });
    });
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
    await page.goto(`/dashboard/store/modules?business=${bakery}`);
    const loyalty = page.getByTestId('module-e2e_loyalty');
    await expect(loyalty.getByTestId('module-cancelled')).toContainText('(cancelled)');
    await loyalty.getByTestId('module-keep').click();
    await expect(toast(page, 'E2E Loyalty is kept')).toBeVisible();
    await expect(loyalty.getByTestId('module-owned')).toBeVisible();
  });

  test('a business with an unpaid invoice buys nothing, and says why', async ({ page }) => {
    const bar = await businessIdOf(page.request, 'Bar La Plaza');
    await page.goto(`/dashboard/store/plans?business=${bar}`);
    await expect(page.getByTestId('store-unpaid')).toContainText('Bar La Plaza has an unpaid invoice');
    await expect(page.getByTestId('store-unpaid')).toContainText('The bank declined the last card.');
    await page.getByTestId('store-period-year').click();
    // ion-button's own native button (in its shadow) is what the browser disables.
    await expect(page.getByTestId('plan-switch').locator('button')).toBeDisabled();
    await expect(page.getByTestId('plan-starter').getByTestId('plan-hint')).toHaveText('Pay the pending invoice first.');
    await page.screenshot({ path: join(SHOTS_DIR, 'store-unpaid-1440.png'), fullPage: true });
  });

  // The admin has not pasted Standard's Stripe price yet: its card does not sell it and says why, instead of
  // «This cannot be bought right now. Contact support.» once pressed.
  test('a plan without its Stripe price is shown but not sold: its button is disabled and says why', async ({ page }) => {
    const errors = watchPageErrors(page);
    const cafe = await businessIdOf(page.request, 'Café Central');
    const restore = withoutStripePrices('standard');
    try {
      for (const size of VIEWPORTS) {
        await page.setViewportSize(size);
        await page.goto(`/dashboard/store/plans?business=${cafe}`);
        const standard = page.getByTestId('plan-standard');
        await expect(standard.getByTestId('plan-upgrade').locator('button')).toBeDisabled();
        await expect(standard.getByTestId('plan-hint')).toHaveText('Not on sale right now');
        await expect(page.getByTestId('plan-starter').getByTestId('plan-upgrade').locator('button')).toBeEnabled();
        await planShot(page, `store-not-on-sale-${size.width}.png`);
      }
    } finally {
      restore();
    }
    expect(errors).toEqual([]);
  });

  test('inside the apps and on the account surface it does not sell: no prices, no Stripe, no link out', async ({ page }) => {
    const stripe = watchStripeRequests(page);
    await page.goto('/dashboard/store/plans?surface=account');
    const notice = page.getByTestId('store-in-app');
    // Already in the browser: why nothing is bought here, not «go to erplora.com in your browser».
    await expect(notice).toContainText('Nothing is bought from here');
    await expect(notice).toContainText('This account was opened from the app, and the app does not sell');
    await expect(page.getByTestId('plan-starter')).toHaveCount(0);
    expect(await page.locator('ion-router-outlet').innerText()).not.toMatch(/€/);
    await page.setViewportSize({ width: 390, height: 844 });
    // flow: none — test tooling. Taken before a frame at the new size, it repeated the top at its bottom.
    await settled(page);
    const png = await page.screenshot({ path: join(SHOTS_DIR, 'store-app-390.png') });
    expect(await repeatedTop(page, png), 'store-app-390.png repeats the top of the page at its bottom').toBe(0);
    // Back to the web for the rest of the session.
    await page.goto('/dashboard/store/plans?surface=web');
    await expect(page.getByTestId('store-plans')).toBeVisible();
    // The Tauri bridge (the installed apps).
    await page.addInitScript(() => {
      (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = {};
    });
    await page.goto('/dashboard/store/modules');
    await expect(page.getByTestId('store-in-app')).toBeVisible();
    await expect(page.getByTestId('module-e2e_bookings')).toHaveCount(0);
    expect(stripe).toEqual([]);
  });

  // flow: none — test tooling. Resized under the spec, the Store is shot as painted at each size: a capture
  // taken before a frame at the new size repeated the top of the page at its bottom (87 rows, 3 in 6 at 390 px).
  test('a screenshot right after a resize is the Store as painted, never its top repeated at the bottom', async ({ page }) => {
    const bakery = await businessIdOf(page.request, 'Panadería López');
    await page.goto(`/dashboard/store/plans?business=${bakery}`);
    await expect(page.getByTestId('store-plans')).toBeVisible();
    expect(await stripedAfterResize(page, VIEWPORTS, 'FIX-SAAS-E2E-STORE-SHOT-STRIPE')).toEqual([]);
  });

  test('plan price and action rows align at desktop, and features expand together from the keyboard', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const cafe = await businessIdOf(page.request, 'Café Central');
    await page.goto(`/dashboard/store/plans?business=${cafe}`);
    const cards = page.locator('.plans-grid > ion-card');
    await expect(cards).toHaveCount(3);
    await expect(cards.first()).toHaveCSS('overflow', 'clip');
    const priceTops = await cards.getByTestId('plan-price').evaluateAll((prices) => prices.map((price) => Math.round(price.getBoundingClientRect().top)));
    const actionTops = await cards.locator('.plan-card__actions').evaluateAll((actions) => actions.map((action) => Math.round(action.getBoundingClientRect().top)));
    expect(new Set(priceTops).size, `price tops: ${priceTops}`).toBe(1);
    expect(new Set(actionTops).size, `action tops: ${actionTops}`).toBe(1);

    const toggles = cards.getByTestId('plan-features-toggle');
    expect(await toggles.count()).toBeGreaterThan(0);
    const collapsed = await cards.evaluateAll((items) => items.map((item) => item.querySelectorAll('ion-item').length));
    await toggles.first().locator('button').focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Show fewer', expanded: true })).toHaveCount(3);
    const expanded = await cards.evaluateAll((items) => items.map((item) => item.querySelectorAll('ion-item').length));
    expect(expanded.some((count, index) => count > collapsed[index])).toBe(true);
    await toggles.first().click();
    await expect(page.getByRole('button', { name: 'Show all features', expanded: false })).toHaveCount(3);
  });

  test('a cancelled plan explains Keep next to its action at desktop and phone', async ({ page }) => {
    putOnPlan('Panadería López', 'starter', true);
    try {
      const bakery = await businessIdOf(page.request, 'Panadería López');
      await page.emulateMedia({ colorScheme: 'light' });
      for (const size of [VIEWPORTS[2], VIEWPORTS[0]]) {
        await page.setViewportSize(size);
        await page.goto(`/dashboard/store/plans?business=${bakery}`);
        const current = page.getByTestId('plan-starter');
        const note = current.getByTestId('plan-note');
        await expect(note).toContainText('Cancelled: Starter until');
        expect(await note.evaluate((element) => element.nextElementSibling?.getAttribute('data-testid'))).toBe('plan-keep');
        await expect(current.getByTestId('plan-keep')).toBeVisible();
        await planShot(page, `store-plans-cancelled-${size.width}-light.png`);
      }
    } finally {
      putOnPlan('Panadería López', 'starter', false);
    }
  });

  for (const { width, height } of [VIEWPORTS[0], { width: 768, height: 1024 }, VIEWPORTS[1], VIEWPORTS[2]]) {
    for (const theme of ['light', 'dark'] as const) {
      test(`Plans and Modules at ${width} px (${theme}): no sideways scroll, no error`, async ({ page }) => {
        const errors = watchPageErrors(page);
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height });
        const bakery = await businessIdOf(page.request, 'Panadería López');
        const cafe = await businessIdOf(page.request, 'Café Central');
        for (const tab of ['plans', 'modules'] as const) {
          await page.goto(`/dashboard/store/${tab}?business=${tab === 'plans' ? cafe : bakery}`);
          await expect(page.getByTestId(`store-${tab}`)).toBeVisible();
          await settled(page);
          expect(await sidewaysScroll(page), `${tab} at ${width}`).toEqual([]);
          if (tab === 'modules') {
            await page.screenshot({ path: join(SHOTS_DIR, `store-modules-${width}-${theme}.png`), fullPage: true });
          }
          if (tab === 'plans') {
            if (width !== 834) await planShot(page, `store-plans-${width}-${theme}.png`);
            const toggle = page.getByTestId('plan-features-toggle').first();
            await expect(page.getByRole('button', { name: 'Show all features', expanded: false }).first()).toBeVisible();
            if (width === 390) {
              const emptyAction = page.getByTestId('plan-free').locator('.plan-card__actions');
              await expect(emptyAction).toHaveCSS('display', 'none');
              expect(await emptyAction.evaluate((element) => element.getBoundingClientRect().height)).toBe(0);
              expect((await toggle.boundingBox())?.height).toBeGreaterThanOrEqual(44);
              const gap = await page.getByTestId('plan-free').evaluate((card) => {
                const price = card.querySelector('[data-testid="plan-price"]')!.getBoundingClientRect();
                const feature = card.querySelector('ion-item')!.getBoundingClientRect();
                return feature.top - price.bottom;
              });
              expect(gap, 'Free has no empty action slot on a phone').toBeLessThanOrEqual(16);
            }
            await toggle.click();
            await expect(page.getByRole('button', { name: 'Show fewer', expanded: true }).first()).toBeVisible();
            await settled(page);
            expect(await sidewaysScroll(page), `expanded plans at ${width}`).toEqual([]);
            if (width !== 834) await planShot(page, `store-plans-${width}-${theme}-expanded.png`);
            await toggle.click();
            await expect(page.getByRole('button', { name: 'Show all features', expanded: false }).first()).toBeVisible();
            await checkPayingPlans(page, bakery, width);
          }
        }
        expect(errors).toEqual([]);
      });
    }
  }
});
