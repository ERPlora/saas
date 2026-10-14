// «Switch to annual» (or back to monthly) on the business's own plan (mockups `store.html` «modal-annual»;
// UX-AUDIT-4 W-F2/X-03/V-37): for THAT business, with what it charges today WITH VAT — Stripe's prorated
// preview — the new price, what it is a month, and that its modules follow the billing. Confirmed with
// `billing.plan.change` at the preview's proration date.
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

import { STARTER } from '../__tests__/fixtures';
import { apiError, flush, mountBilling } from '../__tests__/mount-billing';
import AnnualSwitchDialog from './AnnualSwitchDialog.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

const PREVIEW = { amount_due_cents: 36288, tax_cents: 6298, currency: 'eur', proration_date: 1792000000, charge_starts_at: null };
const SUBSCRIPTION = {
  hub_id: 'plaza',
  plan: 'starter',
  billing_interval: 'year',
  status: 'active',
  cancel_at_period_end: false,
  current_period_end: '2027-10-31T12:00:00Z',
  trial_end: null,
  modules: [],
};

async function setup(api: (path: string) => Response, interval: 'year' | 'month' = 'year', locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const done = vi.fn();
  const Host = {
    render: () =>
      h(AnnualSwitchDialog, {
        business: { id: 'plaza', name: 'Bar La Plaza' },
        plan: STARTER,
        interval,
        open: open.value,
        'onUpdate:open': (v: boolean) => (open.value = v),
        onDone: done,
      }),
  };
  const m = await mountBilling(Host, { locale, api: (call) => api(new URL(call.url, 'http://localhost').pathname) });
  await flush();
  return { ...m, open, done };
}

const rows = (s: Awaited<ReturnType<typeof setup>>) =>
  s.qa('annual-row').map((row) => [...row.children].map((cell) => cell.textContent?.trim()).join(' '));

describe('AnnualSwitchDialog', () => {
  it('names the business, and says what it charges today with VAT, the new price and its month', async () => {
    const s = await setup(() => Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: PREVIEW }));
    expect(s.calls()).toEqual([
      { method: 'POST', path: '/api/billing/checkout/start', body: { hub_id: 'plaza', plan: 'starter', interval: 'year' }, query: {} },
    ]);
    expect(s.q('annual-modal')?.getAttribute('aria-label')).toBe('Switch to Starter annual');
    expect(s.q('annual-intro')?.textContent?.trim()).toBe('Bar La Plaza · Starter is billed annually from now on.');
    expect(rows(s)).toEqual([
      'Today (prorated) €299.90 + VAT',
      'VAT €62.98',
      'Charged today, with VAT €362.88',
      'Starter annual €299.90/year + VAT',
      'Equivalent to €24.99/month + VAT',
    ]);
    expect(s.q('annual-modules')?.textContent?.trim()).toBe('Its modules are billed annually too.');
    expect(s.q('annual-modal-submit')?.textContent?.trim()).toBe('Switch to annual');
  });

  it('confirms at the preview’s proration date, for this business, and says it', async () => {
    const s = await setup((path) =>
      path.endsWith('/change') ? Response.json(SUBSCRIPTION) : Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: PREVIEW }),
    );
    s.q('annual-modal-submit')?.click();
    await flush();
    expect(s.calls().at(-1)).toEqual({
      method: 'POST',
      path: '/api/billing/plan/change',
      body: { hub_id: 'plaza', plan: 'starter', interval: 'year', proration_date: 1792000000 },
      query: {},
    });
    expect(toastSuccess).toHaveBeenCalledWith('Bar La Plaza is now on Starter, billed annually');
    expect(s.done).toHaveBeenCalledWith(SUBSCRIPTION);
    expect(s.open.value).toBe(false);
  });

  it('back to monthly says the monthly price, without a month’s equivalent', async () => {
    const s = await setup(() => Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: { ...PREVIEW, amount_due_cents: 0, tax_cents: 0 } }), 'month');
    expect(s.q('annual-modal')?.getAttribute('aria-label')).toBe('Switch to Starter monthly');
    expect(rows(s).at(-1)).toBe('Starter monthly €29.99/month + VAT');
    expect(s.q('annual-modal-submit')?.textContent?.trim()).toBe('Switch to monthly');
  });

  it('a refusal says why, and nothing changes', async () => {
    const s = await setup(() => apiError(409, 'billing.invoice_unpaid', 'This business has an unpaid invoice: pay it before buying or changing anything.'));
    expect(s.q('annual-modal-error')?.textContent).toContain('This business has an unpaid invoice');
    expect((s.q('annual-modal-submit') as unknown as { disabled: boolean }).disabled).toBe(true);
  });

  it('says the money in an Ionic list: one ion-item per line, its amount an ion-note at the end', async () => {
    const s = await setup(() => Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: PREVIEW }));
    const rows = s.qa('annual-row');
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.tagName === 'ION-ITEM' && row.closest('ion-list'))).toBe(true);
    expect(rows.every((row) => row.querySelector('ion-label') && row.querySelector('ion-note[slot="end"]'))).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup(() => Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: PREVIEW }), 'year', 'es');
    expect(s.q('annual-modal')?.getAttribute('aria-label')).toBe('Cambiar a Starter anual');
    expect(rows(s)[2]).toBe('Se cobra hoy, con IVA 362,88 €');
  });
});
