// Several businesses with an unpaid invoice (audit 2026-10-14, R-15; mockups `businesses.html`): one notice,
// not one per business — the suspended first, each line its own sentence (the day, never the minute) and,
// on the web, its own way to pay (`UnpaidActions`); inside the apps, where to pay, without a button.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { mountHubs } from '../__tests__/mount-hubs';
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
});
