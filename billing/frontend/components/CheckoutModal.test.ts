// Buying for a business Stripe does not bill yet (PLAN-SAAS §3.2 and §4; mockups `store.html`
// «modal-checkout»; UX-AUDIT-4 W-06/X-02/X-09): Stripe's Embedded Checkout inside our dialog.
//   - First who pays (`hubs.billing_profile.get`): without a name, a country and a postal code, the form
//     comes first and is saved (`hubs.billing_profile.update`); otherwise «Invoice to … · Change».
//   - Then `billing.checkout.start` (the plan at the billing chosen, with the promo code; or the module,
//     named in the title) gives a Checkout Session's `client_secret`; Stripe.js (web only) mounts it with
//     `createEmbeddedCheckoutPage({ fetchClientSecret })` inside the dialog.
//   - Stripe's `onComplete` → «Paying…», the checkout is destroyed and the page goes to the business,
//     saying what happened. A failure is always said, with «Retry» (saas#1565: never a silent spinner).
//   - Closing destroys the checkout. The declined card is never offered: Stripe asks for a card, and the
//     dialog says why when the account's card was declined.
// Stripe cannot run here: `window.Stripe` is a double (`__tests__/stripe-double.ts`).
import { applySurface } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
vi.mock('../stripe-js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../stripe-js')>()),
  loadStripeJs: vi.fn(),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { apiError, flush, mountBilling } from '../__tests__/mount-billing';
import { stripeDouble, type StripeDouble } from '../__tests__/stripe-double';
import { loadStripeJs } from '../stripe-js';
import CheckoutModal, { type CheckoutPurchase } from './CheckoutModal.vue';

let stripe: StripeDouble;

beforeEach(() => {
  stripe = stripeDouble();
  vi.mocked(loadStripeJs).mockImplementation(() => Promise.resolve(stripe.factory as never));
});

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(loadStripeJs).mockReset();
  applySurface('web');
  document.body.innerHTML = '';
});

const PROFILE = {
  hub_id: 'cafe',
  paid_by_another_account: false,
  billing_name: 'Café Central SL',
  tax_id: 'ESB12345678',
  billing_address: 'Calle Mayor 1',
  billing_city: 'Madrid',
  billing_postal_code: '28001',
  billing_country: 'ES',
  billing_email: '',
  same_as_business: false,
};
const EMPTY_PROFILE = { ...PROFILE, billing_name: '', tax_id: '', billing_address: '', billing_city: '', billing_postal_code: '', billing_country: '' };
const SESSION = { flow: 'checkout', session_id: 'cs_test_1', client_secret: 'cs_test_1_secret_x', publishable_key: 'pk_test_double', preview: null };
const PLAN: CheckoutPurchase = { kind: 'plan', slug: 'starter', name: 'Starter', interval: 'year' };
const MODULE: CheckoutPurchase = { kind: 'module', slug: 'booking', name: 'Bookings', interval: 'month' };

type Handler = (call: { method: string; path: string; body: unknown }) => Response | Promise<Response>;

const happy: Handler = ({ path }) => {
  if (path === '/api/hubs/billing-profile') return Response.json(PROFILE);
  if (path === '/api/billing/checkout/start') return Response.json(SESSION);
  return Response.json({});
};

async function setup(api: Handler = happy, purchase: CheckoutPurchase = PLAN, extra: Record<string, unknown> = {}) {
  const open = ref(true);
  const stale = vi.fn();
  const Host = {
    render: () =>
      h(CheckoutModal, {
        business: { id: 'cafe', name: 'Café Central' },
        purchase,
        promoCode: 'SPRING',
        declinedCard: false,
        ...extra,
        open: open.value,
        'onUpdate:open': (v: boolean) => (open.value = v),
        onStale: stale,
      }),
  };
  const m = await mountBilling(Host, {
    api: (call) => {
      const url = new URL(call.url, 'http://localhost');
      const body = typeof call.init.body === 'string' ? JSON.parse(call.init.body) : undefined;
      return api({ method: (call.init.method ?? 'GET').toUpperCase(), path: url.pathname, body });
    },
  });
  await flush();
  await flush();
  return { ...m, open, stale };
}

describe('CheckoutModal', () => {
  it('with the payer on file, opens Stripe’s Embedded Checkout for the plan at the billing chosen', async () => {
    const s = await setup();
    expect(s.calls().map((c) => [c.method, c.path, c.body ?? c.query])).toEqual([
      ['GET', '/api/hubs/billing-profile', { hub_id: 'cafe' }],
      ['POST', '/api/billing/checkout/start', { hub_id: 'cafe', plan: 'starter', interval: 'year', promo_code: 'SPRING' }],
    ]);
    expect(s.q('checkout-modal')?.getAttribute('aria-label')).toBe('Upgrade to Starter');
    expect(s.q('checkout-for')?.textContent?.trim()).toBe('For Café Central · renews every year');
    expect(s.q('checkout-invoice-to')?.textContent?.replace(/\s+/g, ' ').trim()).toContain('Café Central SL · ESB12345678');
    expect(s.q('checkout-invoice-to')?.tagName).toBe('ION-ITEM');
    expect(s.q('checkout-change-details')?.tagName).toBe('ION-BUTTON');
    expect(s.q('checkout-change-details')?.querySelector('ion-icon')).not.toBeNull();
    expect(stripe.keys).toEqual(['pk_test_double']);
    expect(stripe.secrets).toEqual(['cs_test_1_secret_x']);
    expect(stripe.checkouts[0].mountedOn).toBe(s.q('checkout-stripe'));
  });

  it('a module is named in the title and bought monthly, without the plan’s promo code', async () => {
    const s = await setup(happy, MODULE);
    expect(s.q('checkout-modal')?.getAttribute('aria-label')).toBe('Add Bookings');
    expect(s.calls()[1].body).toEqual({ hub_id: 'cafe', module: 'booking', interval: 'month' });
  });

  it('once Stripe completes the payment: «Paying…», the checkout destroyed, the business’s page and what happened', async () => {
    const s = await setup();
    stripe.complete();
    await s.wrapper.vm.$nextTick();
    expect(s.q('checkout-paying')?.textContent?.trim()).toBe('Paying…');
    await flush();
    expect(stripe.checkouts[0].destroyed).toBe(true);
    expect(toastSuccess).toHaveBeenCalledWith('Café Central is now on Starter');
    expect(s.router.currentRoute.value.fullPath).toBe('/businesses/cafe/summary');
    expect(s.open.value).toBe(false);
  });

  it('a module bought says it turns on by itself', async () => {
    const s = await setup(happy, MODULE);
    stripe.complete();
    await flush();
    expect(toastSuccess).toHaveBeenCalledWith('Bookings added to Café Central: it turns on in a few seconds');
    expect(s.router.currentRoute.value.fullPath).toBe('/businesses/cafe/summary');
  });

  it('without the payer’s details, asks them first, saves them and then pays', async () => {
    let saved: unknown;
    const s = await setup(({ path, method, body }) => {
      if (path === '/api/hubs/billing-profile' && method === 'GET') return Response.json(EMPTY_PROFILE);
      if (path === '/api/hubs/billing-profile') {
        saved = body;
        return Response.json({ ...PROFILE, ...(body as object) });
      }
      return Response.json(SESSION);
    });
    expect(s.q('details-name')).not.toBeNull();
    expect(stripe.checkouts).toEqual([]);
    expect((s.q('checkout-modal-submit') as unknown as { disabled: boolean }).disabled).toBe(true);
    for (const [id, value] of [['name', 'Café Central SL'], ['postal-code', '28001']]) {
      s.q(`details-${id}`)?.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    }
    s.q('details-country')?.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'ES' } }));
    await flush();
    expect(s.q('checkout-modal-submit')?.textContent?.trim()).toBe('Continue to payment');
    s.q('checkout-modal-submit')?.click();
    await flush();
    await flush();
    expect(saved).toEqual({
      hub_id: 'cafe',
      billing_name: 'Café Central SL',
      tax_id: '',
      billing_address: '',
      billing_city: '',
      billing_postal_code: '28001',
      billing_country: 'ES',
      billing_email: '',
      same_as_business: false,
    });
    expect(stripe.checkouts).toHaveLength(1);
  });

  it('a payer that is another account’s is asked again', async () => {
    const s = await setup(({ path }) => (path === '/api/hubs/billing-profile' ? Response.json({ ...EMPTY_PROFILE, paid_by_another_account: true }) : Response.json(SESSION)));
    expect(s.q('checkout-another-account')?.textContent).toContain('Another account paid for this business until now');
  });

  it('a place the tax cannot be worked out for sends back to the details, with the server’s reason', async () => {
    const s = await setup(({ path }) =>
      path === '/api/hubs/billing-profile'
        ? Response.json(PROFILE)
        : apiError(409, 'billing.billing_location_required', 'Say where the payer is: the tax depends on it.'),
    );
    expect(s.q('details-postal-code')).not.toBeNull();
    expect(s.q('checkout-modal-error')?.textContent).toContain('Say where the payer is: the tax depends on it.');
    expect(stripe.checkouts).toEqual([]);
  });

  it('«Change» goes back to the details and lets the checkout go', async () => {
    const s = await setup();
    s.q('checkout-change-details')?.click();
    await flush();
    expect(stripe.checkouts[0].destroyed).toBe(true);
    expect(s.q('details-name')).not.toBeNull();
  });

  it('Stripe.js that does not load is said, and «Retry» tries again (never a silent spinner)', async () => {
    vi.mocked(loadStripeJs).mockImplementationOnce(() => Promise.reject(new Error('Stripe.js could not be loaded')));
    const s = await setup();
    expect(s.q('checkout-error')?.textContent).toContain('We could not open the secure payment');
    expect(s.q('checkout-error')?.textContent).toContain('Nothing was charged. Check your connection and try again.');
    s.q('checkout-retry')?.click();
    await flush();
    await flush();
    expect(stripe.checkouts).toHaveLength(1);
  });

  it('a checkout Stripe refuses to mount is said too', async () => {
    stripe.failNext(new Error('Invalid client secret'));
    const s = await setup();
    expect(s.q('checkout-error')?.textContent).toContain('We could not open the secure payment');
  });

  it('a refusal of the server is said in the person’s words', async () => {
    const s = await setup(({ path }) => (path === '/api/hubs/billing-profile' ? Response.json(PROFILE) : apiError(503, 'billing.payments_unavailable', 'Payments are not available right now.')));
    expect(s.q('checkout-error')?.textContent).toContain('Payments are not available right now.');
  });

  it('a business that already pays goes back to the Store, which asks the price again', async () => {
    const s = await setup(({ path }) =>
      path === '/api/hubs/billing-profile'
        ? Response.json(PROFILE)
        : Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: { amount_due_cents: 1, tax_cents: 0, currency: 'eur', proration_date: 1, charge_starts_at: null } }),
    );
    expect(s.stale).toHaveBeenCalled();
    expect(s.open.value).toBe(false);
    expect(stripe.checkouts).toEqual([]);
  });

  it('closing the dialog lets the checkout go', async () => {
    const s = await setup();
    s.open.value = false;
    await flush();
    expect(stripe.checkouts[0].destroyed).toBe(true);
  });

  it('when the account’s card was declined, says to pay with another', async () => {
    const s = await setup(happy, PLAN, { declinedCard: true });
    expect(s.q('checkout-declined')?.textContent).toContain('The card on your account was declined: pay with another one.');
  });

  it('off the web it starts nothing: the apps sell nothing', async () => {
    applySurface('desktop');
    const s = await setup();
    expect(s.calls().filter((c) => c.path.startsWith('/api/billing'))).toEqual([]);
    expect(loadStripeJs).not.toHaveBeenCalled();
  });
});
