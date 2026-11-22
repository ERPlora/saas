// The Store's checkout: a business on Free buys a plan or a module there, at the billing of the switch and with
// its promo code, and is told whose card was declined; one that turns out to pay already is priced again. The
// checkout has its own tests: here it is a stub, and what the shop hands it is checked.
import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { toastInfo } from '@erplora/ui/shell';

import { BAKERY, CAFE, PLAZA } from '../__tests__/fixtures';
import { flush } from '../__tests__/mount-billing';
import { setup, setUpStoreShop } from '../__tests__/store-shop';
import CheckoutModal from './CheckoutModal.vue';

beforeEach(() => {
  // The shop compares a module's `valid_until` with now (`apply`): the fixtures end on Oct 31, 2026, so the
  // clock stays before it. Only the date: the timers stay real (the harness has its own fake clock).
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-20T10:00:00Z'));
});

setUpStoreShop();

describe('StoreShop', () => {
  it('on Free a plan is bought in the checkout, at the billing of the switch, with the promo code', async () => {
    const s = await setup({
      businessId: 'cafe',
      answer: ({ path, query }) => (path === '/api/billing/promo-check' ? Response.json({ code: query.code.toUpperCase(), valid: true, trial_days: 30, discount: null }) : undefined),
    });
    expect(s.el('store-period').text()).toContain('Annual · −17 %');
    s.el('store-period').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'year' } }));
    await flush();
    await s.el('store-promo-toggle').trigger('click');
    s.el('store-promo-code').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'spring' } }));
    await s.el('store-promo-apply').trigger('click');
    await flush();
    await s.el('plan-upgrade').trigger('click');
    const checkout = s.wrapper.findComponent(CheckoutModal);
    expect(checkout.props()).toMatchObject({
      open: true,
      business: { id: 'cafe', name: 'Café Central' },
      purchase: { kind: 'plan', slug: 'starter', name: 'Starter', interval: 'year' },
      promoCode: 'SPRING',
      // Bar La Plaza's card was declined, but Café Central has a payer of its own.
      declinedFor: null,
    });
  });

  it('a code of a discount: the checkout says it, when the plan’s price starts and that nothing is charged today', async () => {
    const testers = { code: 'TESTERS', valid: true, trial_days: 0, discount: { percent_off: 100, amount_off_cents: null, currency: 'eur', duration: 'repeating', duration_in_months: 6, applies_to: { kind: 'plans', plans: [], intervals: ['month'] } } };
    const s = await setup({ businessId: 'cafe', answer: ({ path }) => (path.endsWith('promo-check') ? Response.json(testers) : undefined) });
    await s.el('store-promo-toggle').trigger('click');
    s.el('store-promo-code').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'testers' } }));
    await s.el('store-promo-apply').trigger('click');
    await flush();
    await s.el('plan-upgrade').trigger('click');
    const notice = mount({ render: () => s.wrapper.findComponent(CheckoutModal).vm.$slots.notice?.({}) }, { global: { plugins: [s.i18n] } });
    expect(notice.text()).toBe('Free for 6 months. Then €29.99/month + VAT. Your card is not charged today.');
  });

  it('the card of the same payer declined: the checkout says whose', async () => {
    const shared = { ...CAFE, payer_id: PLAZA.payer_id };
    const s = await setup({ businessId: 'cafe', rows: [BAKERY, shared, PLAZA] });
    await s.el('plan-upgrade').trigger('click');
    expect(s.wrapper.findComponent(CheckoutModal).props()).toMatchObject({ declinedFor: 'Bar La Plaza' });
  });

  it('an invalid promo code is said, and none is sent', async () => {
    const s = await setup({
      businessId: 'cafe',
      answer: ({ path }) => (path === '/api/billing/promo-check' ? Response.json({ code: 'NOPE', valid: false, trial_days: 0, discount: null }) : undefined),
    });
    await s.el('store-promo-toggle').trigger('click');
    s.el('store-promo-code').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'nope' } }));
    await s.el('store-promo-apply').trigger('click');
    await flush();
    await s.el('plan-upgrade').trigger('click');
    expect(s.wrapper.findComponent(CheckoutModal).props('promoCode')).toBe('');
  });

  it('on Free a module is bought in the checkout too, named', async () => {
    const s = await setup({ businessId: 'cafe', tab: 'modules' });
    await s.el('module-booking').find('[data-testid="module-add"]').trigger('click');
    expect(s.wrapper.findComponent(CheckoutModal).props()).toMatchObject({
      open: true,
      purchase: { kind: 'module', slug: 'booking', name: 'Bookings', interval: 'month' },
    });
  });

  it('a business that turns out to pay already asks the catalog again and says the price changed', async () => {
    const s = await setup({ businessId: 'cafe' });
    const before = s.calls().filter((c) => c.path === '/api/billing/store').length;
    s.wrapper.findComponent(CheckoutModal).vm.$emit('stale');
    await flush();
    expect(s.calls().filter((c) => c.path === '/api/billing/store').length).toBe(before + 1);
    expect(toastInfo).toHaveBeenCalledWith('This business already pays: the price changed, check it again.');
  });
});
