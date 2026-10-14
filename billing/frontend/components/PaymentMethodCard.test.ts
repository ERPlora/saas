// Billing → Payment details: the card of one payer (mockups `billing.html` «payment»; README §4 and §6.18):
// the brand and last four, when it expires and which businesses it pays; the last charge that failed; and,
// on the web, «Change card» (Stripe's Customer Portal, «the secure payment page») — the main action after a
// failure. Inside the apps, how to change it, without a button nor a link. Stripe away: it says so.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { paymentMethod } from '../__tests__/billing-fixtures';
import { flush, ionProps, mountBilling } from '../__tests__/mount-billing';
import { browser } from '../browser';
import PaymentMethodCard from './PaymentMethodCard.vue';

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

async function card(method = paymentMethod(), locale: 'en' | 'es' = 'en', api?: () => Response) {
  const s = await mountBilling(PaymentMethodCard, { props: { method }, locale, api });
  return { ...s, q: (id: string) => s.wrapper.find(`[data-testid="${id}"]`) };
}

describe('PaymentMethodCard', () => {
  it('says the card, when it expires and which businesses it pays', async () => {
    const s = await card();
    expect(s.q('payment-card').text()).toBe('Visa •••• 4242');
    expect(s.q('payment-card-detail').text()).toBe('Expires 08/28 · pays Panadería López and Bar La Plaza');
    expect(s.q('payment-failed').exists()).toBe(false);
    expect(ionProps(s.q('payment-change'), 'fill')).toEqual({ fill: 'outline' });
    expect(s.q('payment-secure').text()).toBe('The secure payment page opens.');
  });

  it('after a failed charge it says when and of which business, and «Change card» is the main action', async () => {
    const s = await card(paymentMethod({ last_failure: { at: '2026-10-10T08:00:00Z', business: 'Bar La Plaza' } }));
    expect(s.q('payment-failed').find('.status-pill').text()).toBe('The last charge failed');
    expect(s.q('payment-failed').find('.card-text').text()).toBe('Oct 10, 2026 · Bar La Plaza');
    expect(ionProps(s.q('payment-change'), 'fill')).toEqual({ fill: 'solid' });
  });

  it('«Change card» opens the Customer Portal of that payer', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await card(paymentMethod(), 'en', () => Response.json({ url: 'https://billing.stripe.com/p/session/x' }));
    await s.q('payment-change').trigger('click');
    await flush();
    expect(s.calls()).toEqual([{ method: 'POST', path: '/api/billing/portal', body: { hub_id: 'bakery' }, query: {} }]);
    expect(assign).toHaveBeenCalledWith('https://billing.stripe.com/p/session/x');
  });

  it('Stripe away, or no card: it says so', async () => {
    expect((await card(paymentMethod({ card: null, unavailable: true }))).q('payment-card-detail').text()).toBe(
      'We cannot show the card right now: try again in a few minutes.',
    );
    const none = await card(paymentMethod({ card: null }));
    expect(none.q('payment-card').text()).toBe('No card saved yet.');
    expect(none.q('payment-card-detail').text()).toBe('Pays Panadería López and Bar La Plaza');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface it says how to change it, without a button nor a link', async (surface) => {
    applySurface(surface);
    const s = await card();
    expect(s.q('payment-change').exists()).toBe(false);
    expect(s.q('payment-app').text()).toBe('To change the card, go to erplora.com in your browser.');
    expect(s.wrapper.findAll('[href]')).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const s = await card(paymentMethod({ card: { brand: 'mastercard', last4: '5454', exp_month: 11, exp_year: 2029 } }), 'es');
    expect(s.q('payment-card').text()).toBe('Mastercard •••• 5454');
    expect(s.q('payment-card-detail').text()).toBe('Caduca 11/29 · paga Panadería López y Bar La Plaza');
    expect(s.q('payment-change').text()).toBe('Cambiar tarjeta');
  });
});
