// What confirming a change charges NOW, before the owner confirms it (PLAN-SAAS §3.2; billing README
// «billing.checkout.start»): for a business Stripe bills already, `billing.checkout.start` answers
// `flow: "confirm"` with Stripe's prorated preview (amount with VAT, the VAT, the proration date the
// confirmation sends back). A business that does not pay yet answers `flow: "checkout"`: the preview says
// so (`checkout`), and the Store opens the Embedded Checkout instead.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { apiError, flush, mountBilling } from './__tests__/mount-billing';
import { useChargePreview } from './charge-preview';

const PREVIEW = { amount_due_cents: 1112, tax_cents: 193, currency: 'eur', proration_date: 1792000000, charge_starts_at: null };

async function setup(api: () => Response | Promise<Response>) {
  let preview!: ReturnType<typeof useChargePreview>;
  const m = await mountBilling(
    defineComponent({
      setup() {
        preview = useChargePreview();
        return () => h('div');
      },
    }),
    { api },
  );
  return { ...m, preview };
}

describe('useChargePreview', () => {
  it('asks billing.checkout.start for what the change charges now, net and VAT apart', async () => {
    const s = await setup(() => Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: PREVIEW }));
    expect(s.preview.state.value).toBe('idle');
    const loading = s.preview.load({ hub_id: 'h1', module: 'booking' });
    expect(s.preview.state.value).toBe('loading');
    await loading;
    expect(s.calls()).toEqual([
      { method: 'POST', path: '/api/billing/checkout/start', body: { hub_id: 'h1', module: 'booking' }, query: {} },
    ]);
    expect(s.preview.state.value).toBe('ready');
    expect(s.preview.preview.value).toEqual(PREVIEW);
    expect(s.preview.netCents.value).toBe(919);
  });

  it('a business Stripe does not bill yet needs the checkout instead', async () => {
    const s = await setup(() => Response.json({ flow: 'checkout', session_id: 'cs_1', client_secret: 'cs_1_secret', publishable_key: 'pk', preview: null }));
    await s.preview.load({ hub_id: 'h1', module: 'booking' });
    expect(s.preview.state.value).toBe('checkout');
    expect(s.preview.preview.value).toBeNull();
  });

  it('a refusal is kept to be said (an unpaid invoice, a module already owned…)', async () => {
    const s = await setup(() => apiError(409, 'billing.invoice_unpaid', 'This business has an unpaid invoice.'));
    await s.preview.load({ hub_id: 'h1', module: 'booking' });
    await flush();
    expect(s.preview.state.value).toBe('error');
    expect(s.preview.error.value).toBeInstanceOf(ApiError);
    expect(s.preview.error.value?.code).toBe('billing.invoice_unpaid');
  });

  it('loading again starts from scratch', async () => {
    let answer: Response = apiError(409, 'billing.preview_expired', 'Out of date.');
    const s = await setup(() => answer);
    await s.preview.load({ hub_id: 'h1', module: 'booking' });
    answer = Response.json({ flow: 'confirm', session_id: null, client_secret: null, publishable_key: null, preview: PREVIEW });
    await s.preview.load({ hub_id: 'h1', module: 'booking' });
    expect(s.preview.state.value).toBe('ready');
    expect(s.preview.error.value).toBeNull();
  });
});
