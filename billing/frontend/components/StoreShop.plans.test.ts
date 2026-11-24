// The Store's plans: which a business is offered (sign-up plans on Free, upgrades once it pays, the internal plan
// ERPlora marked it for), the month or year switch, and changing, switching, cancelling or keeping its plan. The
// dialogs have their own tests: here they are stubs, and what the shop hands them is checked.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import { catalog, FREE_SUBSCRIPTION, MAX, PAYMENT_TEST, PLANS, PRO, plan, subscription } from '../__tests__/fixtures';
import { flush, ionProps } from '../__tests__/mount-billing';
import { setup, setUpStoreShop } from '../__tests__/store-shop';
import AnnualSwitchDialog from './AnnualSwitchDialog.vue';
import CheckoutModal from './CheckoutModal.vue';
import ProrationDialog from './ProrationDialog.vue';

beforeEach(() => {
  // The shop compares a module's `valid_until` with now (`apply`): the fixtures end on Oct 31, 2026, so the
  // clock stays before it. Only the date: the timers stay real (the harness has its own fake clock).
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-20T10:00:00Z'));
});

setUpStoreShop();

/** Café Central once ERPlora's staff marked it: offered the internal plan, whose card only its catalog brings. */
const MARKED_CAFE = catalog('cafe', {
  subscription: FREE_SUBSCRIPTION,
  offered_plans: ['starter', 'standard', 'payment-test'],
  internal_plans: [PAYMENT_TEST],
});

describe('StoreShop', () => {
  it('a Free business is offered the plans sold at sign-up; the upgrades wait for a paid plan', async () => {
    const plans = { ...PLANS, plans: [...PLANS.plans, PRO, MAX] };
    const s = await setup({ businessId: 'cafe', answer: ({ path }) => (path === '/api/plans' ? Response.json(plans) : undefined) });
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter']);
    expect(s.el('store-plans-later').text()).toBe('Pro and Max: available after moving to Starter.');
  });

  it('a paying business is offered the upgrades, and nothing waits', async () => {
    const plans = { ...PLANS, plans: [...PLANS.plans, PRO, MAX] };
    const s = await setup({ answer: ({ path }) => (path === '/api/plans' ? Response.json(plans) : undefined) });
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter', 'Pro', 'Max']);
    expect(s.el('store-plans-later').exists()).toBe(false);
  });

  it('a business ERPlora marked is offered the internal plan with the card its catalog brings, and buys it', async () => {
    const s = await setup({ businessId: 'cafe', answer: ({ path }) => (path === '/api/billing/store' ? Response.json(MARKED_CAFE) : undefined) });
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter', 'Payment Test (internal)']);
    await s.el('plan-payment-test').find('[data-testid="plan-upgrade"]').trigger('click');
    expect(s.wrapper.findComponent(CheckoutModal).props()).toMatchObject({
      open: true,
      business: { id: 'cafe' },
      purchase: { kind: 'plan', slug: 'payment-test', name: 'Payment Test (internal)', interval: 'month' },
    });
  });

  it('the internal plan of one business is never shown for another: each catalog brings its own', async () => {
    const s = await setup({ businessId: 'cafe', answer: ({ path, query }) => (path === '/api/billing/store' && query.hub_id === 'cafe' ? Response.json(MARKED_CAFE) : undefined) });
    expect(s.el('plan-payment-test').exists()).toBe(true);
    await s.pick('bakery');
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter']);
  });

  it('a business on an internal plan sees its card as its current plan', async () => {
    const onIt = catalog('bakery', { subscription: subscription({ plan: 'payment-test' }), internal_plans: [PAYMENT_TEST] });
    const s = await setup({ answer: ({ path }) => (path === '/api/billing/store' ? Response.json(onIt) : undefined) });
    expect(s.el('plan-payment-test').find('[data-testid="plan-current"]').exists()).toBe(true);
  });

  it('cancelling an internal plan names it, as its card does', async () => {
    const onIt = catalog('bakery', { subscription: subscription({ plan: 'payment-test' }), internal_plans: [PAYMENT_TEST] });
    const s = await setup({ answer: ({ path }) => (path === '/api/billing/store' ? Response.json(onIt) : undefined) });
    await s.el('plan-downgrade').trigger('click');
    await flush();
    expect(document.querySelector('[data-testid="store-cancel"]')?.textContent).toContain('Panadería López · Payment Test (internal)');
  });

  it('the billing switch is Ionic’s segment (month · year), and choosing a year moves every price to the year’s', async () => {
    const s = await setup({ businessId: 'cafe' });
    const segment = s.el('store-period');
    expect(segment.element.tagName).toBe('ION-SEGMENT');
    expect(ionProps(segment, 'value')).toEqual({ value: 'month' });
    const buttons = segment.findAll('ion-segment-button');
    expect(buttons.map((b) => [(b.element as unknown as { value: string }).value, b.text()])).toEqual([
      ['month', 'Monthly'],
      ['year', 'Annual · −17 %'],
    ]);
    expect(s.el('plan-starter').find('[data-testid="plan-price"]').text()).toBe('€29.99 /month + VAT');
    segment.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'year' } }));
    await flush();
    expect(ionProps(s.el('store-period'), 'value')).toEqual({ value: 'year' });
    expect(s.el('plan-starter').find('[data-testid="plan-price"]').text()).toBe('€299.90 /year + VAT · €24.99/month');
  });

  it('a paying business changes plan with its proration', async () => {
    const pro = { ...PLANS.plans[1], slug: 'pro', name: 'Pro', price_monthly: '59.99', price_annual: '599.90' };
    const s = await setup({ answer: ({ path }) => (path === '/api/plans' ? Response.json({ ...PLANS, plans: [...PLANS.plans, pro] }) : undefined) });
    await s.el('plan-pro').find('[data-testid="plan-change"]').trigger('click');
    expect(s.wrapper.findComponent(ProrationDialog).props('item')).toEqual({ kind: 'plan', slug: 'pro', name: 'Pro', from: 'Starter', recurringCents: 5999, interval: 'month' });
  });

  it('a plan Stripe has no price for is shown, but its card does not sell it and says why', async () => {
    const unsold = catalog('bakery', { offered_plans: ['starter', 'pro'], sold_intervals: { starter: ['month', 'year'], pro: [] } });
    const plans = { ...PLANS, plans: [...PLANS.plans, PRO] };
    const s = await setup({
      answer: ({ path }) => (path === '/api/plans' ? Response.json(plans) : path === '/api/billing/store' ? Response.json(unsold) : undefined),
    });
    const change = s.el('plan-pro').find('[data-testid="plan-change"]');
    expect((change.element as unknown as { disabled: boolean }).disabled).toBe(true);
    expect(s.el('plan-pro').find('[data-testid="plan-hint"]').text()).toBe('Not on sale right now');
    await change.trigger('click');
    expect(s.wrapper.findComponent(ProrationDialog).props('item')).toBeNull();
  });

  it('its own plan switches to annual in its dialog, for that business', async () => {
    const s = await setup();
    s.el('store-period').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'year' } }));
    await flush();
    await s.el('plan-switch').trigger('click');
    const dialog = s.wrapper.findComponent(AnnualSwitchDialog);
    expect(dialog.props()).toMatchObject({ open: true, business: { id: 'bakery', name: 'Panadería López' }, interval: 'year' });
    expect(dialog.props('plan')).toMatchObject({ slug: 'starter' });
  });

  it('«Downgrade to Free» confirms with the dates and Free’s limits, and cancels at the end of the period', async () => {
    const s = await setup({
      answer: ({ path }) =>
        path === '/api/billing/plan/cancel'
          ? Response.json({ hub_id: 'bakery', plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: true, current_period_end: '2026-10-31T12:00:00Z', trial_end: null, modules: [] })
          : undefined,
    });
    await s.el('plan-downgrade').trigger('click');
    await flush();
    const dialog = document.querySelector('[data-testid="store-cancel"]');
    expect(dialog?.textContent).toContain('Panadería López · Starter');
    expect(dialog?.textContent).toContain('It stays on Starter until Oct 31, 2026; then it goes to Free and is not charged again.');
    expect(dialog?.textContent).toContain('Free covers 3 users and 1 device at a time.');
    expect(dialog?.textContent).toContain('Until then you can undo it with «Keep the plan».');
    expect((document.querySelector('[data-testid="store-cancel-submit"] ion-icon') as unknown as { name?: string }).name).toBe('close-circle-outline');
    (document.querySelector('[data-testid="store-cancel-submit"]') as HTMLElement).click();
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ method: 'POST', path: '/api/billing/plan/cancel', body: { hub_id: 'bakery' } });
    expect(toastSuccess).toHaveBeenCalledWith('Plan cancelled: Starter until Oct 31, 2026');
    expect(s.el('plan-free').find('[data-testid="plan-note"]').text()).toBe('The business goes to Free on Oct 31, 2026.');
    expect(s.el('plan-keep').exists()).toBe(true);
  });

  it('«Keep the plan» undoes the cancellation and says when it renews', async () => {
    const cancelled = catalog('bakery', { subscription: subscription({ cancel_at_period_end: true }) });
    const s = await setup({
      answer: ({ path }) => {
        if (path === '/api/billing/store') return Response.json(cancelled);
        if (path === '/api/billing/plan/keep') {
          return Response.json({ hub_id: 'bakery', plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: '2026-10-31T12:00:00Z', trial_end: null, modules: [] });
        }
        return undefined;
      },
    });
    await s.el('plan-keep').trigger('click');
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ path: '/api/billing/plan/keep', body: { hub_id: 'bakery' } });
    expect(toastSuccess).toHaveBeenCalledWith('Starter is kept: it renews on Oct 31, 2026');
    expect(s.el('plan-keep').exists()).toBe(false);
  });

  it('a downgrade that waits: its own card names the plan it moves to, and «Keep the plan» undoes it', async () => {
    const STANDARD = plan('standard', 'Standard', '59.99', '599.90');
    const waiting = catalog('bakery', {
      subscription: subscription({ plan: 'standard', scheduled_change: { plan: 'starter', interval: 'month', starts_at: '2026-10-31T12:00:00Z' } }),
    });
    const s = await setup({
      answer: ({ path }) => {
        if (path === '/api/plans') return Response.json({ ...PLANS, plans: [...PLANS.plans, STANDARD] });
        if (path === '/api/billing/store') return Response.json(waiting);
        if (path === '/api/billing/plan/keep') {
          return Response.json({ hub_id: 'bakery', plan: 'standard', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: '2026-10-31T12:00:00Z', trial_end: null, modules: [], scheduled_change: null });
        }
        return undefined;
      },
    });
    expect(s.el('plan-standard').find('[data-testid="plan-note"]').text()).toBe('Downgrade scheduled: Standard until Oct 31, 2026, then Starter.');
    expect(s.el('plan-starter').find('[data-testid="plan-note"]').text()).toBe('The business moves to Starter on Oct 31, 2026.');
    await s.el('plan-keep').trigger('click');
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ path: '/api/billing/plan/keep', body: { hub_id: 'bakery' } });
    expect(toastSuccess).toHaveBeenCalledWith('Standard is kept: it renews on Oct 31, 2026');
    expect(s.el('plan-keep').exists()).toBe(false);
    expect(s.el('plan-standard').find('[data-testid="plan-note"]').exists()).toBe(false);
    expect(s.el('plan-starter').find('[data-testid="plan-change"]').exists()).toBe(true);
  });

  it('a downgrade confirmed in its dialog shows at once on the card, before the catalog is asked again', async () => {
    const STANDARD = plan('standard', 'Standard', '59.99', '599.90');
    const s = await setup({
      answer: ({ path }) => {
        if (path === '/api/plans') return Response.json({ ...PLANS, plans: [...PLANS.plans, STANDARD] });
        if (path === '/api/billing/store') return Response.json(catalog('bakery', { subscription: subscription({ plan: 'standard' }) }));
        return undefined;
      },
    });
    s.wrapper.findComponent(ProrationDialog).vm.$emit('done', {
      hub_id: 'bakery',
      plan: 'standard',
      billing_interval: 'month',
      status: 'active',
      cancel_at_period_end: false,
      current_period_end: '2026-10-31T12:00:00Z',
      trial_end: null,
      modules: [],
      scheduled_change: { plan: 'starter', interval: 'month', starts_at: '2026-10-31T12:00:00Z' },
    });
    await flush();
    expect(s.el('plan-standard').find('[data-testid="plan-note"]').text()).toBe('Downgrade scheduled: Standard until Oct 31, 2026, then Starter.');
    expect(s.el('plan-keep').exists()).toBe(true);
  });
});
