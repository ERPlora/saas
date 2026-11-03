// Several businesses with an unpaid invoice (audit 2026-10-14, R-15; mockups `businesses.html`): one notice,
// not one per business — the suspended first, each line its own sentence (the day, never the minute) and,
// on the web, its own way to pay (`UnpaidActions`); inside the apps, where to pay, without a button.
// clock: data only — no code under test compares these dates with now.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { invoicePage, unpaidRow } from '../../../billing/frontend/__tests__/billing-fixtures';
import { ionProps, mountHubs } from '../__tests__/mount-hubs';
import UnpaidGroupNotice from './UnpaidGroupNotice.vue';

const business = (id: string, name: string, extra: Record<string, unknown>) => ({
  id,
  name,
  status: 'past_due',
  unpaid_reason: 'payment_failed',
  unpaid_since: '2026-10-10T14:23:00Z',
  pay_url: `https://invoice.stripe.com/i/${id}`,
  ...extra,
});

afterEach(() => {
  applySurface('web');
  document.body.innerHTML = '';
});

describe('UnpaidGroupNotice', () => {
  it('lists the suspended first, then the ones about to be, each with its way to pay', async () => {
    const { wrapper } = await mountHubs(UnpaidGroupNotice, {
      props: {
        businesses: [
          business('plaza', 'Bar La Plaza', {}),
          business('norte', 'Bar Norte', { status: 'suspended', unpaid_since: '2026-10-09T08:00:00Z' }),
          business('cafe', 'Café Central', { unpaid_since: null, pay_url: null }),
        ],
      },
    });
    expect(wrapper.text()).toContain('3 businesses have unpaid invoices');
    const lines = wrapper.findAll('[data-testid="businesses-unpaid-line"]');
    expect(lines.map((line) => line.find('.unpaid-line__text').text())).toEqual([
      'Bar Norte is suspended since Oct 9, 2026.',
      'Bar La Plaza is suspended on Oct 17, 2026 if it is not paid.',
      'Café Central has an unpaid invoice.',
    ]);
    expect(lines[0].find('[data-testid="unpaid-pay"]').exists()).toBe(true);
    // Whoever may not pay it (no `pay_url`) gets no button.
    expect(lines[2].find('ion-button').exists()).toBe(false);
  });

  it('a suspended business without its date, and a declined card, are said too', async () => {
    const { wrapper } = await mountHubs(UnpaidGroupNotice, {
      locale: 'es',
      props: {
        businesses: [
          business('plaza', 'Bar La Plaza', { unpaid_reason: 'card_declined' }),
          business('norte', 'Bar Norte', { status: 'suspended', unpaid_since: null }),
        ],
      },
    });
    const lines = wrapper.findAll('[data-testid="businesses-unpaid-line"]');
    expect(lines[0].find('.unpaid-line__text').text()).toBe('Bar Norte está suspendido.');
    expect(lines[1].find('.unpaid-line__text').text()).toBe(
      'Bar La Plaza se suspende el 17 oct 2026 si no se paga. El banco rechazó la tarjeta.',
    );
  });

  it('the most urgent first: the suspended, then the one suspended soonest, as Billing orders them (audit 2 S-07)', async () => {
    const { wrapper } = await mountHubs(UnpaidGroupNotice, {
      props: {
        businesses: [
          business('norte', 'Bar Norte', { unpaid_since: '2026-10-12T08:00:00Z' }),
          business('plaza', 'Bar La Plaza', { unpaid_since: '2026-10-10T08:00:00Z' }),
          business('cafe', 'Café Central', { status: 'suspended', unpaid_since: '2026-10-08T08:00:00Z' }),
        ],
      },
    });
    const names = wrapper.findAll('[data-testid="businesses-unpaid-line"]').map((line) => line.find('.unpaid-line__text').text().split(' is ')[0]);
    expect(names).toEqual(['Café Central', 'Bar La Plaza', 'Bar Norte']);
  });

  it('only the most urgent business’s way out is filled; the others are outlined (audit 2 S-06)', async () => {
    const { wrapper } = await mountHubs(UnpaidGroupNotice, {
      props: {
        businesses: [
          business('norte', 'Bar Norte', { unpaid_since: '2026-10-12T08:00:00Z' }),
          business('plaza', 'Bar La Plaza', { unpaid_since: '2026-10-10T08:00:00Z', unpaid_reason: 'card_declined' }),
        ],
      },
    });
    const lines = wrapper.findAll('[data-testid="businesses-unpaid-line"]');
    expect(ionProps(lines[0].get('[data-testid="unpaid-change-card"]'), 'fill')).toEqual({ fill: 'solid' });
    expect(ionProps(lines[1].get('[data-testid="unpaid-pay"]'), 'fill')).toEqual({ fill: 'outline' });
  });

  it('says how much each business owes and in all, from the unpaid invoices the account sees (audit 2 S-08)', async () => {
    const m = await mountHubs(UnpaidGroupNotice, {
      locale: 'es',
      props: {
        businesses: [business('plaza', 'Bar La Plaza', {}), business('norte', 'Bar Norte', { unpaid_since: '2026-10-12T08:00:00Z' })],
      },
    });
    const call = await m.live();
    await m.result(
      call,
      'billing.invoice.list',
      invoicePage([
        unpaidRow('i1', { business: { id: 'plaza', name: 'Bar La Plaza' }, total_cents: 3629 }),
        unpaidRow('i2', { business: { id: 'norte', name: 'Bar Norte' }, total_cents: 3629 }),
      ]),
    );
    expect(m.wrapper.text()).toContain('2 negocios tienen facturas sin pagar: 72,58\u00a0€');
    const amounts = m.wrapper.findAll('[data-testid="businesses-unpaid-amount"]').map((amount) => amount.text());
    expect(amounts).toEqual(['36,29\u00a0€', '36,29\u00a0€']);
  });

  it('without the invoices (not the account’s, or not loaded) it says the businesses without amounts', async () => {
    const { wrapper } = await mountHubs(UnpaidGroupNotice, {
      props: { businesses: [business('plaza', 'Bar La Plaza', {}), business('norte', 'Bar Norte', {})] },
    });
    expect(wrapper.text()).toContain('2 businesses have unpaid invoices');
    expect(wrapper.find('[data-testid="businesses-unpaid-amount"]').exists()).toBe(false);
  });
});
