// The notice of an unpaid invoice (mockups `businesses.html`, `business.html` «past-due»; README §4 and
// §6.18): since when it is unpaid and until when the business keeps working; on the web, «Pay the
// invoice» (Stripe's page, `pay_url`) when the account may pay it — waiting for another card when the
// bank declined it — and inside the apps how to settle it, without a link.
// clock: data only — no code under test compares these dates with now.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { ionProps, mountHubs } from '../__tests__/mount-hubs';
import UnpaidNotice from './UnpaidNotice.vue';

const PAST_DUE = {
  id: 'plaza',
  name: 'Bar La Plaza',
  status: 'past_due',
  unpaid_reason: 'payment_failed',
  unpaid_since: '2026-10-10T10:00:00Z',
  pay_url: 'https://invoice.stripe.com/i/abc',
};

afterEach(() => {
  applySurface('web');
  document.body.innerHTML = '';
});

const mountNotice = (business: Record<string, unknown>, locale: 'en' | 'es' = 'en') =>
  mountHubs(UnpaidNotice, { props: { business: { ...PAST_DUE, ...business } }, locale });

describe('UnpaidNotice', () => {
  it('says since when and until when it keeps working, and offers to pay on Stripe', async () => {
    const { wrapper } = await mountNotice({});
    expect(wrapper.text()).toContain('Bar La Plaza has an unpaid invoice');
    // The day, never the minute (audit 2026-10-14, R-15).
    expect(wrapper.get('[data-testid="unpaid-body"]').text()).toBe(
      'Unpaid since Oct 10, 2026. It keeps working until Oct 17, 2026; if it is not paid by then, the business is suspended. Nothing is deleted.',
    );
    const pay = wrapper.get('[data-testid="unpaid-pay"]');
    expect(pay.text()).toContain('Pay the invoice');
    expect(ionProps(pay, 'href', 'disabled')).toEqual({ href: 'https://invoice.stripe.com/i/abc', disabled: false });
  });

  it('without a way to pay for this account (not the owner), no button', async () => {
    const { wrapper } = await mountNotice({ pay_url: null });
    expect(wrapper.find('[data-testid="unpaid-pay"]').exists()).toBe(false);
  });

  it('a declined card: «Change card» is the way out (R-09), «Pay» waits for another card, and says so', async () => {
    const { wrapper } = await mountNotice({ unpaid_reason: 'card_declined' });
    expect(ionProps(wrapper.get('[data-testid="unpaid-pay"]'), 'disabled')).toEqual({ disabled: true });
    expect(wrapper.get('[data-testid="unpaid-change-card"]').text()).toContain('Change card');
    expect(wrapper.get('[data-testid="unpaid-card"]').text()).toBe('The bank declined the card: change it before paying.');
  });

  it('suspended, it says so; in Spanish too', async () => {
    const { wrapper } = await mountNotice({ status: 'suspended' }, 'es');
    expect(wrapper.text()).toContain('Bar La Plaza está suspendido');
    expect(wrapper.get('[data-testid="unpaid-body"]').text()).toBe(
      'Sin pagar desde el 10 oct 2026 y suspendido hasta que se pague. No se borra nada: en cuanto se pague vuelve a funcionar.',
    );
    expect(wrapper.get('[data-testid="unpaid-pay"]').text()).toContain('Pagar la factura');
  });

  it('inside the apps: how to settle it, without a button nor a link', async () => {
    applySurface('desktop');
    const { wrapper } = await mountNotice({ unpaid_reason: 'card_declined' });
    expect(wrapper.find('[data-testid="unpaid-pay"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="unpaid-change-card"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="unpaid-app"]').text()).toBe('Settle it from erplora.com, in your browser.');
    expect(wrapper.find('a').exists()).toBe(false);
  });

  it('without a date of its own, the general sentence: no number of days it cannot know (audit R-06)', async () => {
    const { wrapper } = await mountNotice({ unpaid_since: null });
    expect(wrapper.get('[data-testid="unpaid-body"]').text()).toBe(
      'If it is not paid soon, the business is suspended. Nothing is deleted.',
    );
  });
});
