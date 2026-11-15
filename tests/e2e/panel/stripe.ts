// Stripe cannot run in the e2e stack (no keys, no network to it): the page gets a double of Stripe.js
// (`playStripe`) and the operations that call Stripe are answered at the API's edge (`answerCheckoutStart`,
// `playStripePortal`), so a spec proves the page up to the `client_secret` request and the checkout's mount, never
// Stripe's own form, the webhook nor a real charge (`store-checkout.spec.ts` with `stripe listen` does).
import type { Page } from '@playwright/test';

/** What the page handed {@link playStripe}'s Stripe.js, and what it did with it. */
export interface StripePlayed {
  /** The publishable key of each `Stripe(key)`. */
  keys: string[];
  /** The `client_secret` of each Embedded Checkout created. */
  secrets: string[];
  /** The `data-testid` of the element each checkout was mounted in. */
  mountedIn: string[];
  /** How many checkouts the page destroyed. */
  destroyed: number;
}

/** The page's `window` once {@link playStripe} ran: what it recorded, and the `onComplete` of the last checkout. */
type StripeWindow = { __stripe: StripePlayed & { complete?: () => void } };

/**
 * Stripe.js as `page` would get it from js.stripe.com: it records what the page hands it ({@link stripeState}), mounts
 * a placeholder (`stripe-double`) where the Embedded Checkout goes and keeps its `onComplete` ({@link payInStripe}).
 */
export async function playStripe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    type Options = { fetchClientSecret: () => Promise<string>; onComplete?: () => void };
    const w = window as unknown as Record<string, unknown> & StripeWindow;
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

/** What {@link playStripe}'s Stripe.js has recorded so far. */
export function stripeState(page: Page): Promise<StripePlayed> {
  return page.evaluate(() => {
    const { keys, secrets, mountedIn, destroyed } = (window as unknown as StripeWindow).__stripe;
    return { keys, secrets, mountedIn, destroyed };
  });
}

/** Stripe says the payment went through: the `onComplete` the page handed its last checkout runs, as Stripe.js does. */
export async function payInStripe(page: Page): Promise<void> {
  await page.evaluate(() => {
    const { complete } = (window as unknown as StripeWindow).__stripe;
    if (!complete) throw new Error('payInStripe: no Embedded Checkout was created with an onComplete');
    complete();
  });
}

/** What `billing.checkout.start` answers for a payment in Stripe's Embedded Checkout: a plan or an app on Free. */
const CHECKOUT = { flow: 'checkout', session_id: 'cs_test_e2e', client_secret: 'cs_test_e2e_secret', publishable_key: 'pk_test_e2e', preview: null };

/**
 * `billing.checkout.start` answered at the API's edge with `answer` (an Embedded Checkout's session by default): what
 * Stripe would open is never asked. Returns the bodies the page sent it, in order, as the page sent them.
 */
export async function answerCheckoutStart(page: Page, answer: object = CHECKOUT): Promise<unknown[]> {
  const started: unknown[] = [];
  await page.route('**/api/billing/checkout/start', async (route) => {
    started.push(route.request().postDataJSON());
    await route.fulfill({ json: answer });
  });
  return started;
}

/**
 * `path` opened where a business on Free pays in Stripe's Embedded Checkout: Stripe.js played ({@link playStripe}) and
 * `billing.checkout.start` answered with a checkout's session. Returns what the page started ({@link answerCheckoutStart}).
 */
export async function gotoWithCheckout(page: Page, path: string): Promise<unknown[]> {
  await playStripe(page);
  const started = await answerCheckoutStart(page);
  await page.goto(path);
  return started;
}

/**
 * The Store's apps of `business` (on Free) with the payment played ({@link gotoWithCheckout}), and «Add» of the paid
 * app `slug`: its payment opens in the checkout. Returns what the page started ({@link answerCheckoutStart}).
 */
export async function addAppInCheckout(page: Page, business: string, slug: string): Promise<unknown[]> {
  const started = await gotoWithCheckout(page, `/dashboard/store/modules?business=${business}`);
  await page.getByTestId(`module-${slug}`).getByTestId('module-add').click();
  return started;
}

/**
 * `path` opened where a business that already pays is charged in the panel's own dialog: `billing.checkout.start`
 * answers what is charged today (`amountDueCents`, `taxCents` of it), prorated now, and Stripe.js is never needed.
 * Returns what the page started ({@link answerCheckoutStart}).
 */
export async function gotoWithCharge(page: Page, path: string, amountDueCents: number, taxCents: number): Promise<unknown[]> {
  const preview = { amount_due_cents: amountDueCents, tax_cents: taxCents, currency: 'eur', proration_date: Math.floor(Date.now() / 1000), charge_starts_at: null };
  const started = await answerCheckoutStart(page, { flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview });
  await page.goto(path);
  return started;
}

/** Where `billing.portal.open` sends the page once {@link playStripePortal} plays it: Stripe's Customer Portal. */
export const STRIPE_PORTAL_URL = 'https://billing.stripe.com/p/session/e2e';

/**
 * Stripe's Customer Portal played: `billing.portal.open` answered with {@link STRIPE_PORTAL_URL}, and the page there a
 * placeholder. Returns the bodies the page sent `billing.portal.open`, in order.
 */
export async function playStripePortal(page: Page): Promise<unknown[]> {
  await page.route(/^https:\/\/billing\.stripe\.com\//, (route) =>
    route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Stripe (test double)</title><p>Stripe (test double)</p>' }),
  );
  const opened: unknown[] = [];
  await page.route('**/api/billing/portal', async (route) => {
    opened.push(route.request().postDataJSON());
    await route.fulfill({ json: { url: STRIPE_PORTAL_URL } });
  });
  return opened;
}
