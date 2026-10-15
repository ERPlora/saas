// Billing → Subscriptions (mockups `billing.html` «subscriptions», «cancelling»; README §3b; UX-AUDIT-4 W-F1,
// W-F7, W-F10, X-15): one row per business Stripe bills (live `billing.subscription.list`) in a DataTable that
// turns into cards up to 1280 px — business, plan (net), its paid modules (net; «(until …)» on one line when
// cancelled), next invoice (with VAT) and status — with ONLY the actions the server computed, in its order:
// «View the invoice» with an unpaid one, «Change plan» (→ the Store with that business), «Keep the plan»,
// «Cancel plan» (its own dialog) and «View invoices». Changing, keeping and cancelling are web only; inside
// the apps a sentence says where to do it. A downgrade waiting for the end of the period says so.
import { DataTable } from '@erplora/ui/components';
import { applySurface } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../../../hubs/frontend/__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { errorFrame, HELLO, resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
import { invoicePage, subscriptionPage, subscriptionRow, unpaidRow } from '../__tests__/billing-fixtures';
import { APPS, PLANS, plan } from '../__tests__/fixtures';
import { apiError, describeCall, flush, mountBilling, type StreamCall } from '../__tests__/mount-billing';
import CancelPlanDialog from './CancelPlanDialog.vue';
import SubscriptionsTab from './SubscriptionsTab.vue';

const viewport = (size: { width: number; height: number }) =>
  (window as unknown as { happyDOM: { setViewport(v: { width: number; height: number }): void } }).happyDOM.setViewport(size);

beforeEach(() => viewport({ width: 1440, height: 900 }));

afterEach(() => {
  viewport({ width: 1024, height: 768 });
  applySurface('web');
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

const BAKERY_SUB = subscriptionRow('bakery', 'Panadería López', {
  modules: [
    { slug: 'booking', interval: 'month', price_cents: 900, source: 'purchase', valid_until: null },
    { slug: 'loyalty', interval: 'month', price_cents: 600, source: 'purchase', valid_until: '2026-10-31T10:00:00Z' },
  ],
  next_invoice: { date: '2026-11-01T10:00:00Z', total_cents: 4718, currency: 'EUR' },
});
const PLAZA_SUB = subscriptionRow('plaza', 'Bar La Plaza', {
  status: 'past_due',
  status_label: 'Payment pending',
  unpaid_invoice_id: 'i9',
  next_invoice: { date: '2026-11-10T10:00:00Z', total_cents: 3629, currency: 'EUR' },
  actions: ['view_invoice', 'cancel_plan', 'view_invoices'],
  can: { change_plan: false, cancel_plan: true, keep_plan: false, view_invoice: true, view_invoices: true },
});
const CANCELLING = subscriptionRow('bakery', 'Panadería López', {
  cancelling: true,
  ends_at: '2026-11-01T10:00:00Z',
  next_invoice: null,
  actions: ['keep_plan', 'view_invoices'],
  can: { change_plan: true, cancel_plan: false, keep_plan: true, view_invoice: false, view_invoices: true },
});

function api(call: ReturnType<typeof describeCall>): Response {
  if (call.path === '/api/apps') return Response.json(APPS);
  if (call.path === '/api/plans') return Response.json({ ...PLANS, plans: [...PLANS.plans, plan('basic', 'Basic', '14.99', '149.90')] });
  if (call.path === '/api/hubs/businesses/detail') return Response.json({ id: call.query.id, seats: { used: 2, limit: null } });
  return Response.json({});
}

async function setup(locale: 'en' | 'es' = 'en', answer: (call: ReturnType<typeof describeCall>) => Response = api) {
  const s = await mountBilling(SubscriptionsTab, { locale, api: (call) => answer(describeCall(call)) });
  const call: StreamCall = await s.live();
  const push = async (op: string, data: unknown, rev = 1) => {
    call.push(resultFrame(s.client.stream.subscriptions(op as never)[0].id, data, rev));
    await flush();
  };
  const table = () => s.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const testid = (id: string) => s.wrapper.find(`[data-testid="${id}"]`);
  const show = async (rows = [BAKERY_SUB, PLAZA_SUB], rev = 1) => {
    await push('billing.invoice.list', invoicePage([unpaidRow('i9')]), rev);
    await push('billing.subscription.list', subscriptionPage(rows), rev);
  };
  const cells = (index: number) => s.wrapper.findAll('[data-testid="subscriptions-row"]')[index].findAll('[role="cell"]').map((cell) => cell.text());
  const actionsOf = (id: string) => s.wrapper.findAll(`[data-testid^="subscriptions-row-${id}-"]`).map((b) => b.attributes('data-testid')!.slice(`subscriptions-row-${id}-`.length));
  return { ...s, call, push, table, prop, testid, show, cells, actionsOf };
}

describe('SubscriptionsTab: the list', () => {
  it('follows one row per business Stripe bills, a list from 1000 px (its modules and next invoice fold first), with the names of the modules', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('billing.subscription.list').map((sub) => sub.params)).toEqual([{ limit: 100 }]);
    await s.show();
    // Audit 2 R-33: three rows turned into cards on a 1024–1180 laptop; R-30: a card does not repeat its title.
    expect(s.table().props()).toMatchObject({
      title: 'Subscriptions',
      views: ['table', 'cards'],
      cardBreakpoint: 1000,
      cardTitleColumn: 'name',
      testid: 'subscriptions',
      searchKeys: ['name'],
    });
    expect(s.prop<Array<{ key: string; priority?: string }>>('columns').filter((c) => c.priority === 'low').map((c) => c.key)).toEqual(['modules', 'next_invoice']);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Business', 'Plan', 'Modules', 'Next invoice', 'Status']);
    expect(s.calls().map((c) => [c.path, c.query])).toEqual([
      ['/api/apps', { premium: 'true' }],
      ['/api/plans', {}],
    ]);
    expect((s.prop<(n: number) => string>('entityLabel'))(2)).toBe('subscriptions');
  });

  it('says each plan and module at its net price, the next invoice with VAT, and the status', async () => {
    const s = await setup();
    await s.show();
    expect(s.cells(0).slice(0, 5)).toEqual([
      'Panadería López',
      'Starter€29.99/month + VAT',
      'Bookings · €9.00/month + VATLoyalty · €6.00/month + VAT (until Oct 31, 2026)',
      'Nov 1, 2026 · €47.18with VAT',
      'Active',
    ]);
    expect(s.cells(1).slice(0, 5)).toEqual(['Bar La Plaza', 'Starter€29.99/month + VAT', '—', 'Nov 10, 2026 · €36.29with VAT', 'Payment pending']);
    // «Payment pending» is the mockups' `st-overdue`: red, as the banner that explains it.
    const tones = s.wrapper.findAll('[data-testid="subscriptions-row"]').map((row) => row.get('.status-pill').attributes('data-tone'));
    expect(tones).toEqual(['success', 'danger']);
    expect(s.wrapper.find('[data-testid="subscription-until"]').classes()).toContain('nowrap');
  });

  it('a cancelled plan: Free from the end of the period, and until when it is active', async () => {
    const s = await setup();
    await s.show([CANCELLING]);
    expect(s.cells(0).slice(3, 5)).toEqual(['Free from Nov 1, 2026', 'Until Nov 1, 2026']);
  });

  it('a downgrade waiting for the end of the period says what it changes to and when', async () => {
    const s = await setup();
    await s.show([subscriptionRow('bakery', 'Panadería López', { scheduled_change: { plan: 'basic', interval: 'month', starts_at: '2026-11-01T10:00:00Z' } })]);
    expect(s.testid('subscription-scheduled').text()).toBe('Changes to Basic on Nov 1, 2026');
  });

  it('one action per row: its first one fixed and labelled; with a «⋮» (Cancel plan), «View invoices» goes in it too (Ioan, 2026-10-14)', async () => {
    const s = await setup();
    await s.show([BAKERY_SUB, PLAZA_SUB]);
    expect(s.prop<Array<Record<string, unknown>>>('actions').map((a) => [a.id, !!a.pinned, !!a.menuOnly, !!a.showLabel])).toEqual([
      ['lead', true, false, false],
      ['view_invoices', false, false, true],
      ['view_invoices_menu', false, true, true],
      ['cancel_plan', false, true, true],
    ]);
    // Mockups (`billing.html`): an unpaid row keeps «View the invoice» and the rest in «⋮»; an active one, «Change plan».
    expect(s.actionsOf('bakery')).toEqual(['lead', 'menu']);
    expect(s.actionsOf('plaza')).toEqual(['lead', 'menu']);
    expect(s.testid('subscriptions-row-bakery-lead').text()).toBe('Change plan');
    expect(s.testid('subscriptions-row-plaza-lead').text()).toBe('View the invoice');
    await s.testid('subscriptions-row-bakery-menu').trigger('click');
    await flush();
    expect(s.testid('subscriptions-row-bakery-view_invoices_menu').text()).toBe('View invoices');
    expect(s.testid('subscriptions-row-bakery-cancel_plan').text()).toBe('Cancel plan');
  });

  it('without a «⋮» (nothing to cancel), «View invoices» stays a button next to the fixed one', async () => {
    const s = await setup();
    await s.show([CANCELLING]);
    expect(s.actionsOf('bakery')).toEqual(['lead', 'view_invoices']);
    expect(s.testid('subscriptions-row-bakery-lead').text()).toBe('Keep the plan');
    expect(s.testid('subscriptions-row-bakery-view_invoices').text()).toBe('View invoices');
  });

  it('«Change plan» opens the Store with that business; «View invoices» and «View the invoice», Invoices filtered', async () => {
    const s = await setup();
    await s.show();
    await s.testid('subscriptions-row-bakery-lead').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/store/plans?business=bakery');
    await s.testid('subscriptions-row-bakery-menu').trigger('click');
    await flush();
    await s.testid('subscriptions-row-bakery-view_invoices_menu').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/billing/invoices?business=bakery');
    await s.testid('subscriptions-row-plaza-lead').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/billing/invoices?business=plaza&status=open');
  });

  it('the list fills the page between the topbar and the tabbar: rows scroll inside, toolbar and footer stay', async () => {
    const s = await setup();
    await s.show();
    expect(s.prop('fill')).toBe(true);
  });

  it('«Cancel plan» opens its dialog with that row, its modules’ names, Free and its unpaid invoice', async () => {
    const s = await setup();
    await s.show();
    await s.testid('subscriptions-row-plaza-menu').trigger('click');
    await flush();
    await s.testid('subscriptions-row-plaza-cancel_plan').trigger('click');
    await flush();
    const dialog = s.wrapper.findComponent(CancelPlanDialog);
    expect(dialog.props('open')).toBe(true);
    expect(dialog.props('row')).toMatchObject(PLAZA_SUB);
    expect(dialog.props('moduleNames')).toMatchObject({ booking: 'Bookings', loyalty: 'Loyalty' });
    expect(dialog.props('freePlan')).toMatchObject({ slug: 'free', max_users: 3, max_devices: 1 });
    expect(dialog.props('unpaid')).toMatchObject({ id: 'i9' });
  });

  it('«Keep the plan» undoes the cancellation and says so', async () => {
    const s = await setup('en', (call) => (call.path === '/api/billing/plan/keep' ? Response.json({}) : api(call)));
    await s.show([CANCELLING]);
    await s.testid('subscriptions-row-bakery-lead').trigger('click');
    await flush();
    expect(s.calls().filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', path: '/api/billing/plan/keep', body: { hub_id: 'bakery' }, query: {} }]);
    expect(toastSuccess).toHaveBeenCalledWith('Panadería López stays on Starter');
  });

  it('a refused «Keep the plan» says why', async () => {
    const s = await setup('en', (call) =>
      call.path === '/api/billing/plan/keep' ? apiError(409, 'billing.invoice_unpaid', 'Pay the pending invoice first.') : api(call),
    );
    await s.show([CANCELLING]);
    await s.testid('subscriptions-row-bakery-lead').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('Pay the pending invoice first.');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface it shows the subscriptions, without changing them, and says where', async (surface) => {
    applySurface(surface);
    const s = await setup();
    await s.show();
    expect(s.actionsOf('bakery')).toEqual(['view_invoices']);
    expect(s.actionsOf('plaza')).toEqual(['lead', 'view_invoices']);
    expect(s.testid('subscriptions-row-plaza-lead').text()).toBe('View the invoice');
    expect(s.testid('subscriptions-app-hint').text()).toBe(
      surface === 'account'
        ? 'This account was opened from the app: plans are not changed nor cancelled from here.'
        : 'To change or cancel a plan, go to erplora.com in your browser.',
    );
    expect(s.wrapper.findComponent(CancelPlanDialog).exists()).toBe(false);
  });

  it('without paid plans it says all are on Free, and offers the plans on the web', async () => {
    const s = await setup();
    await s.show([]);
    expect(s.testid('subscriptions-empty').text()).toContain('All your businesses are on Free');
    expect(s.testid('subscriptions-empty').text()).toContain('Without a paid plan there is no subscription and nothing is charged.');
    expect(s.testid('subscriptions-empty-plans').attributes('routerlink')).toBe('/store/plans');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es', (call) => (call.path === '/api/apps' ? Response.json({ apps: [{ ...APPS.apps[0], name: 'Reservas' }, { ...APPS.apps[1], name: 'Fidelización' }] }) : api(call)));
    await s.show([{ ...BAKERY_SUB, status_label: 'Activa' }]);
    expect(s.prop('title')).toBe('Suscripciones');
    expect(s.cells(0).slice(0, 5)).toEqual([
      'Panadería López',
      'Starter29,99\u00a0€/mes + IVA',
      'Reservas · 9,00\u00a0€/mes + IVAFidelización · 6,00\u00a0€/mes + IVA (hasta el 31 oct 2026)',
      '1 nov 2026 · 47,18\u00a0€con IVA',
      'Activa',
    ]);
  });
});

describe('SubscriptionsTab: a list that does not load says so, never «All your businesses are on Free» (audit 2026-10-14, R-04)', () => {
  const state = (s: Awaited<ReturnType<typeof setup>>) => ({
    error: s.prop<string | undefined>('error'),
    loading: s.prop<boolean>('loading'),
    retry: s.testid('subscriptions-retry').exists(),
    empty: s.testid('subscriptions-empty').exists(),
  });

  it('a query that fails: the reason and «Retry», not the empty state', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.client.stream.subscriptions('billing.subscription.list')[0].id, 'internal_error'));
    await flush();
    expect(state(s)).toEqual({ error: 'msg internal_error', loading: false, retry: true, empty: false });
  });

  it('nothing in time: an error with «Retry», never a spinner for ever', async () => {
    const s = await setup();
    // The time limit counts from the mount (opening the stream already took 150 ms of it).
    await s.clock.advance(LIVE_TIMEOUT_MS - 1 - s.clock.now());
    expect(s.prop('loading')).toBe(true);
    await s.clock.advance(1);
    expect(state(s)).toEqual({ error: 'Check your connection and try again.', loading: false, retry: true, empty: false });
  });

  it('the stream refused (/api/live answers 503): it could not load, it does not say every business is on Free', async () => {
    const s = await mountBilling(SubscriptionsTab, { api: (call) => api(describeCall(call)) });
    s.liveDown.value = true;
    await s.clock.advance(150);
    expect(s.wrapper.find('[data-testid="subscriptions-retry"]').exists()).toBe(true);
    expect(s.wrapper.find('[data-testid="subscriptions-empty"]').exists()).toBe(false);
    expect(s.wrapper.text()).not.toContain('All your businesses are on Free');
  });

  it('«Retry» opens the stream again and shows the subscriptions that come', async () => {
    const s = await setup();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    await s.testid('subscriptions-retry').trigger('click');
    await flush();
    await s.clock.advance(150);
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.prop('loading')).toBe(true);
    const again = s.net.lastStream();
    again.push(HELLO);
    again.push(resultFrame(s.client.stream.subscriptions('billing.subscription.list')[0].id, subscriptionPage([BAKERY_SUB, PLAZA_SUB]), 1));
    await flush();
    expect(s.wrapper.findAll('[data-testid="subscriptions-row"]')).toHaveLength(2);
    expect(s.prop('error')).toBeUndefined();
  });

  it('the unpaid invoices failing do not block the subscriptions', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, 'internal_error'));
    await s.push('billing.subscription.list', subscriptionPage([BAKERY_SUB, PLAZA_SUB]));
    expect(s.wrapper.findAll('[data-testid="subscriptions-row"]')).toHaveLength(2);
    expect(s.prop('error')).toBeUndefined();
  });

  it('says it in Spanish', async () => {
    const s = await setup('es');
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.prop('error')).toBe('Comprueba tu conexión y vuelve a intentarlo.');
    expect(s.prop<Record<string, string>>('labels')).toMatchObject({ loadError: 'No hemos podido cargar tus suscripciones', retry: 'Reintentar' });
  });
});
