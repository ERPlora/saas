// The checkout dialog mounted alone for its tests, as the Store opens it: Café Central, a payer on file and a
// Checkout Session the server opens. A test file mocks `@ionic/vue`, `@erplora/ui/shell` and `../stripe-js` itself.
import { vi } from 'vitest';
import { h, ref } from 'vue';

import CheckoutModal, { type CheckoutPurchase } from '../components/CheckoutModal.vue';
import { flush, mountBilling } from './mount-billing';

export const PROFILE = {
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
export const EMPTY_PROFILE = { ...PROFILE, billing_name: '', tax_id: '', billing_address: '', billing_city: '', billing_postal_code: '', billing_country: '' };
export const SESSION = { flow: 'checkout', session_id: 'cs_test_1', client_secret: 'cs_test_1_secret_x', publishable_key: 'pk_test_double', preview: null };
export const PLAN: CheckoutPurchase = { kind: 'plan', slug: 'starter', name: 'Starter', interval: 'year' };
export const MODULE: CheckoutPurchase = { kind: 'module', slug: 'booking', name: 'Bookings', interval: 'month' };
/** The plan of a handed-over business, kept with the new owner's card from the end of the paid period. */
export const TAKE_OVER: CheckoutPurchase = { kind: 'takeover', slug: 'starter', name: 'Starter', interval: 'month', from: '2026-11-01T10:00:00Z' };
export const takeOver: Handler = ({ path }) => {
  if (path === '/api/hubs/billing-profile') return Response.json(PROFILE);
  if (path === '/api/billing/plan/take-over') return Response.json(SESSION);
  return Response.json({});
};

export type Handler = (call: { method: string; path: string; body: unknown }) => Response | Promise<Response>;

export const happy: Handler = ({ path }) => {
  if (path === '/api/hubs/billing-profile') return Response.json(PROFILE);
  if (path === '/api/billing/checkout/start') return Response.json(SESSION);
  return Response.json({});
};

export async function setup(api: Handler = happy, purchase: CheckoutPurchase = PLAN, extra: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en', slots = {}) {
  const open = ref(true);
  const stale = vi.fn();
  const Host = {
    render: () =>
      h(CheckoutModal, {
        business: { id: 'cafe', name: 'Café Central' },
        purchase,
        promoCode: 'SPRING',
        declinedFor: null,
        ...extra,
        open: open.value,
        'onUpdate:open': (v: boolean) => (open.value = v),
        onStale: stale,
      }, slots),
  };
  const m = await mountBilling(Host, {
    locale,
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
