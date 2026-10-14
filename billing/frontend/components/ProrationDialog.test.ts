// Adding a module to, or changing the plan of, a business Stripe bills already (PLAN-SAAS §3.2; mockups
// `store.html` «modal-confirm»; UX-AUDIT-4 W-F4: one dialog per module, with ITS proration): no checkout,
// an item of the business's subscription, charged now and prorated. The dialog asks Stripe's preview first
// (`billing.checkout.start`) and says it to the cent — today without VAT, the VAT, the total, and what it
// costs from the renewal — then confirms with the preview's proration date (`billing.checkout.confirm` for
// a module, `billing.plan.change` for a plan). A refusal stays in the dialog; an out-of-date price is asked
// again and said.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { apiError, flush, mountBilling } from '../__tests__/mount-billing';
import ProrationDialog, { type ProrationItem } from './ProrationDialog.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

const PREVIEW = { amount_due_cents: 1112, tax_cents: 193, currency: 'eur', proration_date: 1792000000, charge_starts_at: null };
const confirmFlow = (preview: Record<string, unknown> = PREVIEW) =>
  Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview });
const SUBSCRIPTION = {
  hub_id: 'bakery',
  plan: 'starter',
  billing_interval: 'month',
  status: 'active',
  cancel_at_period_end: false,
  current_period_end: '2026-10-31T12:00:00Z',
  trial_end: null,
  modules: [{ slug: 'booking', source: 'purchase', valid_until: null }],
};
const MODULE: ProrationItem = { kind: 'module', slug: 'booking', name: 'Bookings', recurringCents: 1500, interval: 'month' };
const PLAN: ProrationItem = { kind: 'plan', slug: 'pro', name: 'Pro', from: 'Starter', recurringCents: 5999, interval: 'month' };

async function setup(api: (call: { path: string; body: unknown }) => Response | Promise<Response>, item: ProrationItem = MODULE, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const done = vi.fn();
  const Host = {
    render: () =>
      h(ProrationDialog, {
        business: { id: 'bakery', name: 'Panadería López' },
        item,
        renewal: '2026-11-01T12:00:00Z',
        promoCode: '',
        open: open.value,
        'onUpdate:open': (v: boolean) => (open.value = v),
        onDone: done,
      }),
  };
  const m = await mountBilling(Host, {
    locale,
    api: (call) => {
      const url = new URL(call.url, 'http://localhost');
      const body = typeof call.init.body === 'string' ? JSON.parse(call.init.body) : undefined;
      return api({ path: url.pathname, body });
    },
  });
  await flush();
  return { ...m, open, done };
}

describe('ProrationDialog', () => {
  it('a module: asks its own proration and says it to the cent before charging anything', async () => {
    const s = await setup(() => confirmFlow());
    expect(s.calls()).toEqual([
      { method: 'POST', path: '/api/billing/checkout/start', body: { hub_id: 'bakery', module: 'booking' }, query: {} },
    ]);
    expect(s.q('proration-modal')?.getAttribute('aria-label')).toBe('Add Bookings');
    expect(s.q('proration-intro')?.textContent?.trim()).toBe('It is added to the subscription of Panadería López.');
    const rows = s.qa('proration-row').map((row) => [...row.children].map((cell) => cell.textContent?.trim()).join(' '));
    expect(rows).toEqual(['Today (prorated) €9.19 + VAT', 'VAT €1.93', 'Total today €11.12', 'From Nov 1, 2026 €15.00/month + VAT']);
    expect(s.q('proration-modal-submit')?.textContent?.trim()).toBe('Pay €11.12 and add');
  });

  it('confirms at the preview’s proration date, says the consequence and hands back the subscription', async () => {
    const s = await setup(({ path }) => (path.endsWith('/confirm') ? Response.json(SUBSCRIPTION) : confirmFlow()));
    s.q('proration-modal-submit')?.click();
    await flush();
    expect(s.calls().at(-1)).toEqual({
      method: 'POST',
      path: '/api/billing/checkout/confirm',
      body: { hub_id: 'bakery', module: 'booking', proration_date: 1792000000 },
      query: {},
    });
    expect(toastSuccess).toHaveBeenCalledWith('Bookings added to Panadería López: it turns on in a few seconds');
    expect(s.done).toHaveBeenCalledWith(SUBSCRIPTION);
    expect(s.open.value).toBe(false);
  });

  it('a plan: changes it at the billing chosen, with the promo code typed', async () => {
    const s = await setup(({ path }) => (path.endsWith('/change') ? Response.json({ ...SUBSCRIPTION, plan: 'pro' }) : confirmFlow({ ...PREVIEW, amount_due_cents: 3630, tax_cents: 630 })), PLAN);
    expect(s.calls()[0].body).toEqual({ hub_id: 'bakery', plan: 'pro', interval: 'month', promo_code: '' });
    expect(s.q('proration-modal')?.getAttribute('aria-label')).toBe('Change to Pro');
    expect(s.q('proration-intro')?.textContent?.trim()).toBe('Panadería López changes from Starter to Pro.');
    expect(s.q('proration-modal-submit')?.textContent?.trim()).toBe('Pay €36.30 and change');
    s.q('proration-modal-submit')?.click();
    await flush();
    expect(s.calls().at(-1)?.body).toEqual({ hub_id: 'bakery', plan: 'pro', interval: 'month', proration_date: 1792000000, promo_code: '' });
    expect(toastSuccess).toHaveBeenCalledWith('Panadería López is now on Pro');
  });

  it('during a trial nothing is charged today: it says from when', async () => {
    const s = await setup(() => confirmFlow({ ...PREVIEW, amount_due_cents: 0, tax_cents: 0, charge_starts_at: 1793527200 }));
    expect(s.q('proration-trial')?.textContent?.trim()).toBe('Nothing is charged today: it is charged from Nov 1, 2026, with the plan.');
    expect(s.q('proration-modal-submit')?.textContent?.trim()).toBe('Add');
  });

  it('a declined card is said in the dialog, which stays open', async () => {
    const s = await setup(({ path }) => (path.endsWith('/confirm') ? apiError(409, 'billing.card_declined', 'The card was declined: nothing was added.') : confirmFlow()));
    s.q('proration-modal-submit')?.click();
    await flush();
    expect(s.q('proration-modal-error')?.textContent).toContain('The card was declined: nothing was added.');
    expect(s.open.value).toBe(true);
    expect(s.done).not.toHaveBeenCalled();
  });

  it('an out-of-date price is asked again and said, never charged blind', async () => {
    let starts = 0;
    const s = await setup(({ path }) => {
      if (path.endsWith('/confirm')) return apiError(409, 'billing.preview_expired', 'The price shown is out of date: review it again.');
      starts += 1;
      return confirmFlow({ ...PREVIEW, proration_date: 1792000000 + starts });
    });
    s.q('proration-modal-submit')?.click();
    await flush();
    expect(starts).toBe(2);
    expect(s.q('proration-modal-error')?.textContent).toContain('The price was out of date: here it is again, check it before confirming.');
    expect(s.open.value).toBe(true);
  });

  it('a preview refused (an unpaid invoice) says why and charges nothing', async () => {
    const s = await setup(() => apiError(409, 'billing.invoice_unpaid', 'This business has an unpaid invoice: pay it before buying or changing anything.'));
    expect(s.q('proration-modal-error')?.textContent).toContain('This business has an unpaid invoice');
    expect((s.q('proration-modal-submit') as unknown as { disabled: boolean }).disabled).toBe(true);
    expect(s.q('proration-retry')).not.toBeNull();
  });

  it('says the money in an Ionic list: one ion-item per line, its amount an ion-note at the end', async () => {
    const s = await setup(() => Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: PREVIEW }));
    const rows = s.qa('proration-row');
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.tagName === 'ION-ITEM' && row.closest('ion-list'))).toBe(true);
    expect(rows.every((row) => row.querySelector('ion-label') && row.querySelector('ion-note[slot="end"]'))).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup(() => confirmFlow(), MODULE, 'es');
    expect(s.q('proration-modal')?.getAttribute('aria-label')).toBe('Añadir Bookings');
    expect(s.q('proration-modal-submit')?.textContent?.trim()).toBe('Pagar 11,12 € y añadir');
  });
});
