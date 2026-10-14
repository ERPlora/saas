// The way out of an unpaid invoice wherever a business is listed (audit 2026-10-14, R-07 and R-09): on the web,
// for whoever may pay it (`pay_url`), «Pay the invoice» (Stripe's page); after a declined card, «Change card»
// (Stripe's Customer Portal, `billing.portal.open`) is the main action and «Pay» waits. Inside the apps nothing:
// the notice says where to pay.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browser } from '../../../billing/frontend/browser';
import { accessibleName, describeCall, flush, ionProps, mountHubs } from '../__tests__/mount-hubs';
import UnpaidActions from './UnpaidActions.vue';

const PAST_DUE = {
  id: 'plaza',
  name: 'Bar La Plaza',
  status: 'past_due',
  unpaid_reason: 'payment_failed',
  pay_url: 'https://invoice.stripe.com/i/abc',
};

afterEach(() => {
  applySurface('web');
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

/** The accessible name of an Ionic button, a link one included (Ionic moves `aria-label` to its shadow `<a>`). */
const nameOf = (el: { element: Element }) =>
  accessibleName(el) ?? el.element.shadowRoot?.querySelector('a')?.getAttribute('aria-label') ?? null;

const mountActions = (business: Record<string, unknown>, extra: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') =>
  mountHubs(UnpaidActions, {
    props: { business: { ...PAST_DUE, ...business }, ...extra },
    locale,
    api: (call) =>
      describeCall(call).path === '/api/billing/portal' ? Response.json({ url: 'https://billing.stripe.com/p/session' }) : Response.json({}),
  });

describe('UnpaidActions', () => {
  it('pays the invoice on Stripe’s page', async () => {
    const { wrapper } = await mountActions({});
    const pay = wrapper.get('[data-testid="unpaid-pay"]');
    expect(pay.text()).toContain('Pay the invoice');
    expect(ionProps(pay, 'href', 'disabled', 'fill')).toEqual({ href: 'https://invoice.stripe.com/i/abc', disabled: false, fill: 'solid' });
    expect(wrapper.find('[data-testid="unpaid-change-card"]').exists()).toBe(false);
  });

  it('after a declined card, «Change card» opens the Customer Portal and «Pay» waits', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => undefined);
    const m = await mountActions({ unpaid_reason: 'card_declined' });
    const change = m.wrapper.get('[data-testid="unpaid-change-card"]');
    expect(change.text()).toContain('Change card');
    expect(ionProps(change, 'fill')).toEqual({ fill: 'solid' });
    expect(ionProps(m.wrapper.get('[data-testid="unpaid-pay"]'), 'disabled', 'fill')).toEqual({ disabled: true, fill: 'outline' });
    await change.trigger('click');
    await flush();
    expect(m.calls().find((c) => c.path === '/api/billing/portal')?.body).toEqual({ hub_id: 'plaza' });
    expect(assign).toHaveBeenCalledWith('https://billing.stripe.com/p/session');
  });

  it('in a list, each button is named with its business', async () => {
    const { wrapper } = await mountActions({ unpaid_reason: 'card_declined' }, { named: true }, 'es');
    expect(nameOf(wrapper.get('[data-testid="unpaid-change-card"]'))).toBe('Cambiar la tarjeta de Bar La Plaza');
    expect(nameOf(wrapper.get('[data-testid="unpaid-pay"]'))).toBe('Pagar la factura de Bar La Plaza');
  });

  it('takes the size asked for; large, only the main button is (the waiting «Pay» stays regular)', async () => {
    const small = await mountActions({ unpaid_reason: 'card_declined' }, { size: 'small' });
    expect(ionProps(small.wrapper.get('[data-testid="unpaid-change-card"]'), 'size')).toEqual({ size: 'small' });
    expect(ionProps(small.wrapper.get('[data-testid="unpaid-pay"]'), 'size')).toEqual({ size: 'small' });
    document.body.innerHTML = '';
    const large = await mountActions({ unpaid_reason: 'card_declined' }, { size: 'large' });
    expect(ionProps(large.wrapper.get('[data-testid="unpaid-change-card"]'), 'size')).toEqual({ size: 'large' });
    expect(ionProps(large.wrapper.get('[data-testid="unpaid-pay"]'), 'size')).toEqual({ size: undefined });
  });

  it('nothing for whoever may not pay it (no `pay_url`)', async () => {
    const { wrapper } = await mountActions({ pay_url: null, unpaid_reason: 'card_declined' });
    expect(wrapper.find('ion-button').exists()).toBe(false);
  });

  it('nothing inside the apps', async () => {
    applySurface('desktop');
    const { wrapper } = await mountActions({ unpaid_reason: 'card_declined' });
    expect(wrapper.find('ion-button').exists()).toBe(false);
  });
});
