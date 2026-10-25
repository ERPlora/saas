// The Store itself, on the web (round 17 §2.10–§2.11; mockups `store.html`; README §3, §4, §6.18;
// UX-AUDIT-4): the business it sells to (`?business=` or the first the account owns), its unpaid invoice
// if any, and then Plans or Modules:
//   - plans of `hubs.plan.list`; modules of `apps.app.list` (name, summary, icon, in the person's language)
//     joined by slug with `billing.store.catalog` (prices, what the business has): a module is sold when
//     its app is premium AND billing has it on sale;
//   - a business on Free buys in the Embedded Checkout; one that pays confirms with its proration — one
//     dialog per module — and its own plan switches billing with the total with VAT;
//   - after buying, «Activating…»; owned, never on sale twice; cancelled, «Keep · no charge today»;
//   - with an unpaid invoice, nothing that charges, for THAT business.
// The dialogs have their own tests: here they are stubs, and what the shop hands them is checked.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastInfo: vi.fn(() => Promise.resolve()),
}));

import { toastInfo, toastSuccess } from '@erplora/ui/shell';

import {
  APPS,
  BAKERY,
  CAFE,
  catalog,
  FREE_SUBSCRIPTION,
  MAX,
  PLANS,
  PLAZA,
  PRO,
  SALON,
  businessPage,
  storeModule,
  subscription,
} from '../__tests__/fixtures';
import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { errorFrame, HELLO, resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
import { apiError, flush, ionProps, mountBilling, optionValue, type StreamCall } from '../__tests__/mount-billing';
import AnnualSwitchDialog from './AnnualSwitchDialog.vue';
import CheckoutModal from './CheckoutModal.vue';
import ProrationDialog from './ProrationDialog.vue';
import StoreShop from './StoreShop.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastInfo).mockClear();
  document.body.innerHTML = '';
});

type Answer = (call: { method: string; path: string; query: Record<string, string>; body: unknown }) => Response | undefined;

/** The server: catalogs by business (Panadería pays Starter, Café is on Free, Bar La Plaza owes). */
const CATALOGS: Record<string, ReturnType<typeof catalog>> = {
  bakery: catalog('bakery', { modules: [storeModule('booking', 900), storeModule('loyalty', 600, { owned: true, source: 'purchase', valid_until: '2026-10-31T12:00:00Z' })] }),
  cafe: catalog('cafe', { subscription: FREE_SUBSCRIPTION }),
  plaza: catalog('plaza'),
};

/** `list`: the account's businesses arrive (`result`, by default), nothing arrives yet (`none`), or the stream
 *  is refused (`down`: `/api/live` answers 503). */
async function setup(
  options: { tab?: 'plans' | 'modules'; businessId?: string; rows?: unknown[]; answer?: Answer; locale?: 'en' | 'es'; list?: 'result' | 'none' | 'down' } = {},
) {
  const answer = options.answer ?? (() => undefined);
  const m = await mountBilling(StoreShop, {
    locale: options.locale,
    props: { tab: options.tab ?? 'plans', businessId: options.businessId },
    stubs: { CheckoutModal: true, ProrationDialog: true, AnnualSwitchDialog: true },
    api: (call) => {
      const url = new URL(call.url, 'http://localhost');
      const described = {
        method: (call.init.method ?? 'GET').toUpperCase(),
        path: url.pathname,
        query: Object.fromEntries(url.searchParams.entries()),
        body: typeof call.init.body === 'string' ? JSON.parse(call.init.body) : undefined,
      };
      const custom = answer(described);
      if (custom) return custom;
      if (described.path === '/api/plans') return Response.json(PLANS);
      if (described.path === '/api/apps') return Response.json(APPS);
      if (described.path === '/api/billing/store') return Response.json(CATALOGS[described.query.hub_id]);
      return Response.json({});
    },
  });
  const list = options.list ?? 'result';
  if (list === 'down') m.liveDown.value = true;
  const stream = list === 'down' ? (await m.clock.advance(150), undefined) : await m.live();
  if (stream && list === 'result') await m.result(stream, 'hubs.business.list', businessPage((options.rows ?? [BAKERY, CAFE, PLAZA, SALON]) as never));
  await flush();
  const el = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const all = (id: string) => m.wrapper.findAll(`[data-testid="${id}"]`);
  const pick = async (id: string) => {
    el('store-business').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: id } }));
    await flush();
  };
  return { ...m, stream: stream as StreamCall, el, all, pick };
}

describe('StoreShop', () => {
  it('sells to the first business the account owns: its businesses to pick, and the plans on sale', async () => {
    const s = await setup();
    expect(s.stream.subs.map((sub) => [sub.op, sub.params])).toEqual([['hubs.business.list', { limit: 100 }]]);
    const options = s.el('store-business').findAll('ion-select-option');
    // Peluquería Ana is managed, not owned: only the owner buys.
    expect(options.map((o) => [optionValue(o), o.text()])).toEqual([
      ['bakery', 'Panadería López · Starter'],
      ['cafe', 'Café Central · Free'],
      ['plaza', 'Bar La Plaza · Starter'],
    ]);
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'bakery' });
    const calls = s.calls().map((c) => [c.path, c.query]);
    expect(calls).toEqual(
      expect.arrayContaining([
        ['/api/plans', {}],
        ['/api/apps', { premium: 'true' }],
        ['/api/billing/store', { hub_id: 'bakery' }],
      ]),
    );
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter']);
    expect(s.el('plan-starter').find('[data-testid="plan-current"]').exists()).toBe(true);
  });

  it('without ?business= it sells to the first business that can buy, not one blocked by an unpaid invoice (audit 2 R-17)', async () => {
    const s = await setup({ rows: [PLAZA, BAKERY, CAFE] });
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'bakery' });
    expect(s.el('store-unpaid').exists()).toBe(false);
  });

  it('a Free business is offered the plans sold at sign-up; the upgrades wait for a paid plan (audit 2 S-03)', async () => {
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

  it('?business= chooses the business it came from', async () => {
    const s = await setup({ businessId: 'cafe' });
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'cafe' });
    expect(s.calls().map((c) => c.query.hub_id).filter(Boolean)).toEqual(['cafe']);
    expect(s.el('plan-upgrade').text()).toBe('Upgrade to Starter');
  });

  it('an unknown ?business= falls back to the first one and says so, until another is picked', async () => {
    const s = await setup({ businessId: 'nope' });
    expect(s.el('store-unknown-business').text()).toContain('We could not find that business among yours: here is Panadería López.');
    await s.pick('cafe');
    expect(s.el('store-unknown-business').exists()).toBe(false);
    expect(s.wrapper.emitted('update:businessId')).toEqual([['cafe']]);
    expect(s.calls().at(-1)?.query).toEqual({ hub_id: 'cafe' });
  });

  it('Modules: the premium apps billing has on sale, named by the catalog and priced by billing', async () => {
    const s = await setup({ tab: 'modules' });
    expect(s.all('module-name').map((n) => n.text())).toEqual(['Bookings', 'Loyalty']);
    expect(s.el('module-booking').find('[data-testid="module-price"]').text()).toBe('€9.00/month + VAT');
    // Loyalty is cancelled but still works: it can be kept.
    expect(s.el('module-loyalty').find('[data-testid="module-keep"]').text()).toBe('Keep · no charge today');
  });

  it('the catalog’s names follow the language: they are asked again when it changes', async () => {
    const s = await setup({ tab: 'modules' });
    const before = s.calls().filter((c) => c.path === '/api/apps').length;
    s.i18n.global.locale.value = 'es';
    await flush();
    expect(s.calls().filter((c) => c.path === '/api/apps').length).toBe(before + 1);
  });

  it('with nothing on sale, it says so', async () => {
    // A business with no module: since saas#2589 one it still has is shown although the catalog lists none.
    const none = catalog('bakery', { modules: [storeModule('booking', 900)] });
    const s = await setup({
      tab: 'modules',
      answer: ({ path, query }) =>
        path === '/api/apps' ? Response.json({ apps: [] }) : path === '/api/billing/store' && query.hub_id === 'bakery' ? Response.json(none) : undefined,
    });
    expect(s.el('store-no-modules').text()).toContain('There are no modules on sale right now.');
  });

  it('a business with an unpaid invoice: says why, where to pay, and nothing charges', async () => {
    const s = await setup({ businessId: 'plaza' });
    const notice = s.el('store-unpaid');
    expect(notice.text()).toContain('Bar La Plaza has an unpaid invoice');
    expect(notice.text()).toContain('The bank declined the last card.');
    expect(s.el('store-unpaid-billing').attributes('routerlink')).toBe('/dashboard/billing?business=plaza');
    // A declined card cannot pay: no «Pay the invoice» until the card changes.
    expect(s.el('store-unpaid-pay').exists()).toBe(false);
    await s.wrapper.setProps({ tab: 'modules' });
    await flush();
    expect((s.el('module-booking').find('[data-testid="module-add"]').element as unknown as { disabled: boolean }).disabled).toBe(true);
  });

  it('once the card changed, the notice offers to pay the invoice', async () => {
    const s = await setup({ businessId: 'plaza', rows: [{ ...PLAZA, unpaid_reason: 'card_changed' }] });
    expect(s.el('store-unpaid').text()).toContain('The card was changed: pay the invoice before adding anything.');
    expect(ionProps(s.el('store-unpaid-pay'), 'href')).toEqual({ href: 'https://invoice.stripe.com/i/plaza' });
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

  it('the promo code is asked with Ionic’s controls: a clear button, an outlined md input and buttons with icons', async () => {
    const s = await setup({ businessId: 'cafe' });
    expect(s.el('store-promo-toggle').element.tagName).toBe('ION-BUTTON');
    expect((s.el('store-promo-toggle').find('ion-icon').element as unknown as { name?: string }).name).toBe('ticket-outline');
    await s.el('store-promo-toggle').trigger('click');
    expect(s.el('store-promo-code').element.tagName).toBe('ION-INPUT');
    expect(ionProps(s.el('store-promo-code'), 'mode', 'fill', 'label')).toEqual({ mode: 'md', fill: 'outline', label: 'Promo code' });
    expect(s.el('store-promo-apply').element.tagName).toBe('ION-BUTTON');
    expect(s.el('store-promo-apply').find('ion-icon').exists()).toBe(true);
  });

  it('on Free a plan is bought in the checkout, at the billing of the switch, with the promo code', async () => {
    const s = await setup({
      businessId: 'cafe',
      answer: ({ path, query }) => (path === '/api/billing/promo-check' ? Response.json({ code: query.code.toUpperCase(), valid: true, trial_days: 30 }) : undefined),
    });
    expect(s.el('store-period').text()).toContain('Annual · −17 %');
    s.el('store-period').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'year' } }));
    await flush();
    await s.el('store-promo-toggle').trigger('click');
    s.el('store-promo-code').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'spring' } }));
    await s.el('store-promo-apply').trigger('click');
    await flush();
    expect(s.el('store-promo-result').text()).toBe('Code SPRING: 30 days free before the first charge.');
    await s.el('plan-upgrade').trigger('click');
    const checkout = s.wrapper.findComponent(CheckoutModal);
    expect(checkout.props()).toMatchObject({
      open: true,
      business: { id: 'cafe', name: 'Café Central' },
      purchase: { kind: 'plan', slug: 'starter', name: 'Starter', interval: 'year' },
      promoCode: 'SPRING',
      // Bar La Plaza's card was declined, but Café Central has a payer of its own (audit 2 R-21).
      declinedFor: null,
    });
  });

  it('the card of the same payer declined: the checkout says whose (audit 2 R-21)', async () => {
    const shared = { ...CAFE, payer_id: PLAZA.payer_id };
    const s = await setup({ businessId: 'cafe', rows: [BAKERY, shared, PLAZA] });
    await s.el('plan-upgrade').trigger('click');
    expect(s.wrapper.findComponent(CheckoutModal).props()).toMatchObject({ declinedFor: 'Bar La Plaza' });
  });

  it('an invalid promo code is said, and none is sent', async () => {
    const s = await setup({
      businessId: 'cafe',
      answer: ({ path }) => (path === '/api/billing/promo-check' ? Response.json({ code: 'NOPE', valid: false, trial_days: 0 }) : undefined),
    });
    await s.el('store-promo-toggle').trigger('click');
    s.el('store-promo-code').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'nope' } }));
    await s.el('store-promo-apply').trigger('click');
    await flush();
    expect(s.el('store-promo-result').text()).toBe('This code is not valid, or it was already used.');
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

  it('a paying business adds a module in ITS dialog, and then it is «Activating…», never on sale twice', async () => {
    const s = await setup({ tab: 'modules' });
    await s.el('module-booking').find('[data-testid="module-add"]').trigger('click');
    const dialog = s.wrapper.findComponent(ProrationDialog);
    expect(dialog.props()).toMatchObject({
      open: true,
      business: { id: 'bakery', name: 'Panadería López' },
      item: { kind: 'module', slug: 'booking', name: 'Bookings', recurringCents: 900, interval: 'month' },
      renewal: '2026-10-31T12:00:00Z',
    });
    dialog.vm.$emit('done', {
      hub_id: 'bakery',
      plan: 'starter',
      billing_interval: 'month',
      status: 'active',
      cancel_at_period_end: false,
      current_period_end: '2026-10-31T12:00:00Z',
      trial_end: null,
      modules: [{ slug: 'booking', source: 'purchase', valid_until: null }, { slug: 'loyalty', source: 'purchase', valid_until: '2026-10-31T12:00:00Z' }],
    });
    await flush();
    expect(s.el('module-booking').find('[data-testid="module-activating"]').text()).toBe('Activating… in Panadería López');
    expect(s.el('module-booking').find('[data-testid="module-add"]').exists()).toBe(false);
  });

  it('a paying business changes plan with its proration', async () => {
    const pro = { ...PLANS.plans[1], slug: 'pro', name: 'Pro', price_monthly: '59.99', price_annual: '599.90' };
    const s = await setup({ answer: ({ path }) => (path === '/api/plans' ? Response.json({ ...PLANS, plans: [...PLANS.plans, pro] }) : undefined) });
    await s.el('plan-pro').find('[data-testid="plan-change"]').trigger('click');
    expect(s.wrapper.findComponent(ProrationDialog).props('item')).toEqual({ kind: 'plan', slug: 'pro', name: 'Pro', from: 'Starter', recurringCents: 5999, interval: 'month' });
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

  it('«Keep · no charge today» keeps a cancelled module and says when it renews', async () => {
    const s = await setup({
      tab: 'modules',
      answer: ({ path }) =>
        path === '/api/billing/module/keep'
          ? Response.json({ hub_id: 'bakery', plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: '2026-10-31T12:00:00Z', trial_end: null, modules: [{ slug: 'loyalty', source: 'purchase', valid_until: null }] })
          : undefined,
    });
    await s.el('module-loyalty').find('[data-testid="module-keep"]').trigger('click');
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ path: '/api/billing/module/keep', body: { hub_id: 'bakery', module: 'loyalty' } });
    expect(toastSuccess).toHaveBeenCalledWith('Loyalty is kept: it renews on Oct 31, 2026');
    expect(s.el('module-loyalty').find('[data-testid="module-owned"]').exists()).toBe(true);
  });

  it('BILLING-G66: «Cancel module» confirms with the date it ends, cancels it, and it can be kept until then', async () => {
    const owned = catalog('bakery', { modules: [storeModule('booking', 900, { owned: true, source: 'purchase' })] });
    const s = await setup({
      tab: 'modules',
      answer: ({ path, query }) => {
        if (path === '/api/billing/store' && query.hub_id === 'bakery') return Response.json(owned);
        if (path === '/api/billing/module/cancel')
          return Response.json({ hub_id: 'bakery', plan: 'starter', billing_interval: 'month', status: 'active', cancel_at_period_end: false, current_period_end: '2026-10-31T12:00:00Z', trial_end: null, modules: [{ slug: 'booking', source: 'purchase', valid_until: '2026-10-31T12:00:00Z' }] });
        return undefined;
      },
    });
    await s.el('module-booking').find('[data-testid="module-cancel"]').trigger('click');
    await flush();
    const dialog = document.querySelector('[data-testid="store-cancel-module"]');
    expect(dialog?.textContent).toContain('Panadería López · Bookings');
    expect(dialog?.textContent).toContain('Bookings keeps working in Panadería López until Oct 31, 2026; then it turns off and is not charged again.');
    expect(dialog?.textContent).toContain('Nothing the business wrote with it is deleted.');
    expect(dialog?.textContent).toContain('Until then you can undo it with «Keep».');
    (document.querySelector('[data-testid="store-cancel-module-submit"]') as HTMLElement).click();
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ method: 'POST', path: '/api/billing/module/cancel', body: { hub_id: 'bakery', module: 'booking' } });
    expect(toastSuccess).toHaveBeenCalledWith('Bookings cancelled: it works until Oct 31, 2026');
    expect(s.el('module-booking').find('[data-testid="module-keep"]').exists()).toBe(true);
    expect(s.el('module-booking').find('[data-testid="module-cancel"]').exists()).toBe(false);
  });

  it('BILLING-G66: a refused cancellation stays in its dialog and says why', async () => {
    const owned = catalog('bakery', { modules: [storeModule('booking', 900, { owned: true, source: 'purchase' })] });
    const s = await setup({
      tab: 'modules',
      answer: ({ path, query }) => {
        if (path === '/api/billing/store' && query.hub_id === 'bakery') return Response.json(owned);
        if (path === '/api/billing/module/cancel') return apiError(409, 'billing.plan_change_pending', 'Undo the scheduled plan change first.');
        return undefined;
      },
    });
    await s.el('module-booking').find('[data-testid="module-cancel"]').trigger('click');
    await flush();
    (document.querySelector('[data-testid="store-cancel-module-submit"]') as HTMLElement).click();
    await flush();
    expect(document.querySelector('[data-testid="store-cancel-module"]')?.textContent).toContain('Undo the scheduled plan change first.');
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(s.el('module-booking').find('[data-testid="module-cancel"]').exists()).toBe(true);
  });

  it('saas#2589: a module off sale the business still pays is shown to cancel it, named by billing if the catalog retired its app', async () => {
    const retired = catalog('bakery', { modules: [storeModule('retired', 500, { owned: true, source: 'purchase', on_sale: false, name: 'Old reports' })] });
    const s = await setup({ tab: 'modules', answer: ({ path, query }) => (path === '/api/billing/store' && query.hub_id === 'bakery' ? Response.json(retired) : undefined) });
    expect(s.el('module-retired').find('[data-testid="module-name"]').text()).toBe('Old reports');
    expect(s.el('module-retired').find('[data-testid="module-off-sale"]').exists()).toBe(true);
    expect(s.el('module-retired').find('[data-testid="module-cancel"]').exists()).toBe(true);
  });

  it('a business that turns out to pay already asks the catalog again and says the price changed', async () => {
    const s = await setup({ businessId: 'cafe' });
    const before = s.calls().filter((c) => c.path === '/api/billing/store').length;
    s.wrapper.findComponent(CheckoutModal).vm.$emit('stale');
    await flush();
    expect(s.calls().filter((c) => c.path === '/api/billing/store').length).toBe(before + 1);
    expect(toastInfo).toHaveBeenCalledWith('This business already pays: the price changed, check it again.');
  });

  it('prices that do not load are said, nothing charged, with «Retry»', async () => {
    let fail = true;
    const s = await setup({ answer: ({ path }) => (path === '/api/plans' && fail ? apiError(502, 'unexpected_response', 'x') : undefined) });
    expect(s.el('store-error').text()).toContain('We could not load the prices');
    expect(s.el('store-error').text()).toContain('Nothing was charged. Try again in a few seconds.');
    fail = false;
    await s.el('store-retry').trigger('click');
    await flush();
    expect(s.el('store-error').exists()).toBe(false);
    expect(s.all('plan-name')).toHaveLength(2);
  });

  it('while it loads, skeleton cards', async () => {
    const s = await setup({ answer: ({ path }) => (path === '/api/billing/store' ? (new Promise(() => {}) as never) : undefined) });
    expect(s.el('store-loading').exists()).toBe(true);
  });

  it('an account that owns no business is told who buys, and where to go', async () => {
    const s = await setup({ rows: [SALON] });
    expect(s.el('store-no-business').text()).toContain('You have no business to buy for');
    expect(s.calls().filter((c) => c.path === '/api/billing/store')).toEqual([]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.text()).toContain('¿Para qué negocio?');
    expect(s.wrapper.text()).toContain('Precios sin IVA.');
  });
});

describe('StoreShop: businesses that do not load are said, never «You have no business to buy for» (audit 2026-10-14, R-04)', () => {
  const states = (s: Awaited<ReturnType<typeof setup>>) => ({
    error: s.el('store-error').exists() ? s.el('store-error').find('.heading').text() : null,
    retry: s.el('store-retry').exists(),
    noBusiness: s.el('store-no-business').exists(),
    loading: s.el('store-loading').exists(),
  });
  const BUSINESSES_ERROR = 'We could not load your businesses';

  it('their query fails: it says so with «Retry», not that there is no business', async () => {
    const s = await setup({ list: 'none' });
    s.stream.push(errorFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, 'internal_error'));
    await flush();
    expect(states(s)).toEqual({ error: BUSINESSES_ERROR, retry: true, noBusiness: false, loading: false });
  });

  it('nothing in time: skeleton cards until the limit, then the error', async () => {
    const s = await setup({ list: 'none' });
    // The time limit counts from the mount (opening the stream already took 150 ms of it).
    await s.clock.advance(LIVE_TIMEOUT_MS - 1 - s.clock.now());
    expect(states(s)).toEqual({ error: null, retry: false, noBusiness: false, loading: true });
    await s.clock.advance(1);
    expect(states(s)).toEqual({ error: BUSINESSES_ERROR, retry: true, noBusiness: false, loading: false });
  });

  it('the stream refused (/api/live answers 503): it could not load them, it does not say there are none', async () => {
    const s = await setup({ list: 'down' });
    expect(states(s)).toEqual({ error: BUSINESSES_ERROR, retry: true, noBusiness: false, loading: false });
  });

  it('«Retry» opens the stream again and sells to the businesses that come', async () => {
    const s = await setup({ list: 'none' });
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    await s.el('store-retry').trigger('click');
    await flush();
    await s.clock.advance(150);
    expect(s.net.streams.length).toBe(before + 1);
    expect(states(s)).toEqual({ error: null, retry: false, noBusiness: false, loading: true });
    const again = s.net.lastStream();
    again.push(HELLO);
    again.push(resultFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, businessPage([BAKERY, CAFE] as never), 1));
    await flush();
    expect(ionProps(s.el('store-business'), 'value')).toEqual({ value: 'bakery' });
    expect(s.all('plan-name').map((n) => n.text())).toEqual(['Free', 'Starter']);
  });

  it('says it in Spanish', async () => {
    const s = await setup({ list: 'down', locale: 'es' });
    expect(s.el('store-error').text()).toContain('No hemos podido cargar tus negocios');
  });
});
