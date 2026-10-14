// What waits for a payment, on top of every tab of Billing (mockups `billing.html`; README §6.18; UX-AUDIT-4
// R2, W-F15): the account's invoices not collected (`billing.invoice.list` with `status=open`, live) with
// the state of their business (`hubs.business.list`, live). On Invoices, its banner, or ONE banner for two or
// more (audit 2026-10-14, R-15); on the other tabs the same warning in one line with a link to it. When one of them is paid — here, in another tab, or at
// Stripe's page and back — «Invoice paid: … is up to date again».
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { invoicePage, invoiceRow, unpaidRow } from '../__tests__/billing-fixtures';
import { businessPage, businessRow, PLAZA } from '../__tests__/fixtures';
import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { errorFrame, HELLO, resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
import { describeCall, flush, mountBilling, type StreamCall } from '../__tests__/mount-billing';
import { PAYING_STORAGE_KEY } from '../pay';
import BillingNotices from './BillingNotices.vue';
import UnpaidGroupNotice from './UnpaidGroupNotice.vue';
import UnpaidInvoiceNotice from './UnpaidInvoiceNotice.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  sessionStorage.clear();
  document.body.innerHTML = '';
});

const NORTE = businessRow('norte', 'Bar Norte', { status: 'suspended', unpaid_reason: 'card_declined', unpaid_since: '2026-10-02T08:00:00Z' });
const OPEN_PLAZA = unpaidRow('i1', { total_cents: 3629 });
const OPEN_NORTE = unpaidRow('i2', { business: { id: 'norte', name: 'Bar Norte' }, total_cents: 3629 });

async function setup(tab = 'invoices', api: (call: ReturnType<typeof describeCall>) => Response = () => Response.json({})) {
  const s = await mountBilling(BillingNotices, { props: { tab }, api: (call) => api(describeCall(call)) });
  const call: StreamCall = await s.live();
  const push = async (op: string, data: unknown, rev = 1) => {
    const sub = s.client.stream.subscriptions(op as never)[0];
    call.push(resultFrame(sub.id, data, rev));
    await flush();
  };
  const show = async (open: unknown[], businesses = [PLAZA, NORTE], rev = 1) => {
    await push('hubs.business.list', businessPage(businesses), rev);
    await push('billing.invoice.list', invoicePage(open as never), rev);
  };
  return { ...s, call, push, show };
}

describe('BillingNotices', () => {
  it('follows the account’s invoices not collected and its businesses', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('billing.invoice.list').map((sub) => sub.params)).toEqual([{ status: 'open', limit: 100 }]);
    expect(s.client.stream.subscriptions('hubs.business.list').map((sub) => sub.params)).toEqual([{ limit: 100 }]);
  });

  it('on Invoices, one invoice not collected: its own banner, with its business', async () => {
    const s = await setup();
    await s.show([OPEN_PLAZA]);
    const notices = s.wrapper.findAllComponents(UnpaidInvoiceNotice);
    expect(notices.map((n) => [n.props('invoice').id, n.props('business')?.id])).toEqual([['i1', 'plaza']]);
    expect(s.wrapper.findAllComponents(UnpaidGroupNotice)).toHaveLength(0);
    expect(s.wrapper.find('[data-testid="billing-unpaid-line"]').exists()).toBe(false);
  });

  it('on Invoices, two or more: ONE banner with every one and its business (R-15)', async () => {
    const s = await setup();
    await s.show([OPEN_PLAZA, OPEN_NORTE]);
    expect(s.wrapper.findAllComponents(UnpaidInvoiceNotice)).toHaveLength(0);
    const groups = s.wrapper.findAllComponents(UnpaidGroupNotice);
    expect(groups).toHaveLength(1);
    expect(groups[0].attributes('data-testid')).toBe('billing-unpaid-group');
    expect(groups[0].props('items').map((item: { invoice: { id: string }; business: { id: string } | null }) => [item.invoice.id, item.business?.id])).toEqual([
      ['i1', 'plaza'],
      ['i2', 'norte'],
    ]);
    expect(s.wrapper.find('[data-testid="billing-unpaid-line"]').exists()).toBe(false);
  });

  it('a credit note is no debt: no banner', async () => {
    const s = await setup();
    await s.show([unpaidRow('c1', { kind: 'credit_note' })]);
    expect(s.wrapper.findAllComponents(UnpaidInvoiceNotice)).toEqual([]);
  });

  it.each(['subscriptions', 'payment'])('on %s, the same warning in one line with a link to the invoice', async (tab) => {
    const s = await setup(tab);
    await s.show([OPEN_PLAZA]);
    expect(s.wrapper.findAllComponents(UnpaidInvoiceNotice)).toEqual([]);
    const line = s.wrapper.get('[data-testid="billing-unpaid-line"]');
    expect(line.attributes('role')).toBe('alert');
    expect(line.get('[data-testid="billing-unpaid-text"]').text()).toBe('Bar La Plaza has an unpaid invoice: €36.29.');
    expect(line.get('a').text()).toBe('View the invoice');
    expect(line.get('a').attributes('href')).toBe('/billing/invoices?business=plaza&status=open');
  });

  it('with several, one line with the count, the sum and a link to all of them', async () => {
    const s = await setup('subscriptions');
    await s.show([OPEN_PLAZA, OPEN_NORTE]);
    const line = s.wrapper.get('[data-testid="billing-unpaid-line"]');
    expect(line.get('[data-testid="billing-unpaid-text"]').text()).toBe('2 unpaid invoices: €72.58.');
    expect(line.get('a').text()).toBe('View the invoices');
    expect(line.get('a').attributes('href')).toBe('/billing/invoices?status=open');
  });

  it('nothing waits: nothing is shown', async () => {
    const s = await setup('subscriptions');
    await s.show([]);
    expect(s.wrapper.text()).toBe('');
  });

  it('an invoice that leaves the list because it was paid: «Invoice paid», once', async () => {
    const s = await setup('invoices', (call) =>
      call.path === '/api/billing/invoices/detail' ? Response.json({ ...invoiceRow(call.query.id, { business: { id: 'plaza', name: 'Bar La Plaza' } }) }) : Response.json({}),
    );
    await s.show([OPEN_PLAZA]);
    await s.show([], [PLAZA, NORTE], 2);
    expect(s.calls().filter((c) => c.path === '/api/billing/invoices/detail')).toEqual([
      { method: 'GET', path: '/api/billing/invoices/detail', body: undefined, query: { id: 'i1' } },
    ]);
    expect(toastSuccess).toHaveBeenCalledExactlyOnceWith('Invoice paid: Bar La Plaza is up to date again');
    await s.show([], [PLAZA, NORTE], 3);
    expect(toastSuccess).toHaveBeenCalledTimes(1);
  });

  it('one that leaves it because it was cancelled says nothing', async () => {
    const s = await setup('invoices', () => Response.json(invoiceRow('i1', { payment_status: 'void', payment_status_label: 'Void' })));
    await s.show([OPEN_PLAZA]);
    await s.show([], [PLAZA], 2);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('back from Stripe’s page with the invoice already paid: «Invoice paid», and it is forgotten', async () => {
    sessionStorage.setItem(PAYING_STORAGE_KEY, 'i1');
    const s = await setup('invoices', () => Response.json(invoiceRow('i1', { business: { id: 'plaza', name: 'Bar La Plaza' } })));
    await s.show([]);
    expect(toastSuccess).toHaveBeenCalledExactlyOnceWith('Invoice paid: Bar La Plaza is up to date again');
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBeNull();
  });

  it('back from Stripe’s page before the payment landed: said when it lands', async () => {
    sessionStorage.setItem(PAYING_STORAGE_KEY, 'i1');
    const s = await setup('invoices', () => Response.json(invoiceRow('i1', { business: { id: 'plaza', name: 'Bar La Plaza' } })));
    await s.show([OPEN_PLAZA]);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBe('i1');
    await s.show([], [PLAZA], 2);
    expect(toastSuccess).toHaveBeenCalledExactlyOnceWith('Invoice paid: Bar La Plaza is up to date again');
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await mountBilling(BillingNotices, { props: { tab: 'payment' }, locale: 'es' });
    const call = await s.live();
    call.push(resultFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, businessPage([PLAZA]), 1));
    call.push(resultFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, invoicePage([OPEN_PLAZA]), 1));
    await flush();
    expect(s.wrapper.get('[data-testid="billing-unpaid-text"]').text()).toBe('Bar La Plaza tiene una factura sin pagar: 36,29\u00a0€.');
    expect(s.wrapper.get('[data-testid="billing-unpaid-line"] a').text()).toBe('Ver la factura');
  });
});

describe('BillingNotices: unpaid invoices that do not load are never read as «nothing owed» (audit 2026-10-14, R-04)', () => {
  const UNKNOWN = 'We could not check whether you have unpaid invoices.';

  it.each(['subscriptions', 'payment'])('on %s, a failed list says it could not check, with «Retry»', async (tab) => {
    const s = await setup(tab);
    s.call.push(errorFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, 'internal_error'));
    await flush();
    const unknown = s.wrapper.get('[data-testid="billing-unpaid-unknown"]');
    expect(unknown.attributes('role')).toBe('status');
    expect(unknown.get('[data-testid="billing-unpaid-unknown-text"]').text()).toBe(UNKNOWN);
    expect(unknown.get('[data-testid="billing-unpaid-retry"]').text()).toBe('Retry');
    expect(s.wrapper.find('[data-testid="billing-unpaid-line"]').exists()).toBe(false);
  });

  it('nothing in time: the same, not silence', async () => {
    const s = await setup('payment');
    await s.clock.advance(LIVE_TIMEOUT_MS - 1 - s.clock.now());
    expect(s.wrapper.text()).toBe('');
    await s.clock.advance(1);
    expect(s.wrapper.get('[data-testid="billing-unpaid-unknown-text"]').text()).toBe(UNKNOWN);
  });

  it('«Retry» opens the stream again and says what is owed', async () => {
    const s = await setup('subscriptions');
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    await s.wrapper.get('[data-testid="billing-unpaid-retry"]').trigger('click');
    await flush();
    await s.clock.advance(150);
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.wrapper.find('[data-testid="billing-unpaid-unknown"]').exists()).toBe(false);
    const again = s.net.lastStream();
    again.push(HELLO);
    again.push(resultFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, businessPage([PLAZA, NORTE]), 1));
    again.push(resultFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, invoicePage([OPEN_PLAZA]), 1));
    await flush();
    expect(s.wrapper.get('[data-testid="billing-unpaid-text"]').text()).toBe('Bar La Plaza has an unpaid invoice: €36.29.');
  });

  it('on Invoices the list itself shows every invoice not collected and says when it fails: no second notice', async () => {
    const s = await setup('invoices');
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.wrapper.find('[data-testid="billing-unpaid-unknown"]').exists()).toBe(false);
  });

  it('says it in Spanish', async () => {
    const s = await mountBilling(BillingNotices, { props: { tab: 'payment' }, locale: 'es' });
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.wrapper.get('[data-testid="billing-unpaid-unknown-text"]').text()).toBe('No hemos podido comprobar si tienes facturas sin pagar.');
    expect(s.wrapper.get('[data-testid="billing-unpaid-retry"]').text()).toBe('Reintentar');
  });
});
