// The Store's notice of a business with an unpaid invoice: why it cannot buy, «Pay the invoice» when the invoice
// can be paid (never with the declined card) and «Go to Billing» for that business.
import { InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { PLAZA } from '../__tests__/fixtures';
import { ionProps, mountBilling } from '../__tests__/mount-billing';
import StoreUnpaidNotice from './StoreUnpaidNotice.vue';

async function setup(props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(StoreUnpaidNotice, { locale, props: { business: PLAZA, block: 'card_declined', ...props } });
  const el = (id: string) => s.wrapper.find(`[data-testid="${id}"]`);
  const notice = () => s.wrapper.findComponent(InlineFeedback as unknown as Component);
  const icons = () => s.wrapper.findAll('ion-button > ion-icon').map((icon) => [icon.attributes('slot'), icon.attributes('aria-hidden')]);
  return { ...s, el, notice, icons };
}

describe('StoreUnpaidNotice', () => {
  it('a declined card: says why, and leads only to Billing for that business', async () => {
    const s = await setup({});
    expect(s.notice().props()).toMatchObject({ tone: 'danger', icon: 'ion:card-outline', role: 'alert', heading: 'Bar La Plaza has an unpaid invoice' });
    expect(s.el('store-unpaid').text()).toBe(
      'Bar La Plaza has an unpaid invoiceThe bank declined the last card. Change the card and pay the invoice before adding anything: we do not charge a declined card again.  Go to Billing',
    );
    expect(s.el('store-unpaid-pay').exists()).toBe(false);
    expect(s.el('store-unpaid-billing').attributes('routerlink')).toBe('/dashboard/billing?business=plaza');
    expect(ionProps(s.el('store-unpaid-billing'), 'size', 'fill')).toEqual({ size: 'small', fill: 'outline' });
    expect(s.icons()).toEqual([['start', 'true']]);
  });

  it('once the card changed, «Pay the invoice» opens the invoice', async () => {
    const s = await setup({ block: 'card_changed' });
    expect(s.el('store-unpaid').text()).toContain('The card was changed: pay the invoice before adding anything.');
    expect(s.el('store-unpaid-pay').text()).toBe('Pay the invoice');
    expect(ionProps(s.el('store-unpaid-pay'), 'href', 'size')).toEqual({ href: 'https://invoice.stripe.com/i/plaza', size: 'small' });
    expect(s.el('store-unpaid-billing').text()).toBe('Go to Billing');
    expect(s.icons()).toEqual([
      ['start', 'true'],
      ['start', 'true'],
    ]);
  });

  it('an invoice not paid: pay it before adding or changing anything', async () => {
    const s = await setup({ block: 'unpaid' });
    expect(s.el('store-unpaid').text()).toContain('Pay the invoice before adding or changing anything.');
    expect(s.el('store-unpaid-pay').exists()).toBe(true);
  });

  it('without a page to pay it, no «Pay the invoice»', async () => {
    const s = await setup({ block: 'unpaid', business: { ...PLAZA, pay_url: null } });
    expect(s.el('store-unpaid-pay').exists()).toBe(false);
    expect(s.el('store-unpaid-billing').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ block: 'card_changed' }, 'es');
    expect(s.el('store-unpaid').text()).toBe(
      'Bar La Plaza tiene una factura sin pagarLa tarjeta ya está cambiada: paga la factura antes de añadir nada.  Pagar la factura Ir a Facturación',
    );
  });
});
