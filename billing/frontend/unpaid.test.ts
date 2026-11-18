// What waits for a payment: each business of the account with an unpaid invoice (payment pending or suspended), with
// its oldest invoice Stripe could not charge when the account sees it. Nothing until both lists answered, so a
// notice never shows without its amount and then grows one. When an invoice is paid — on any screen, in another tab,
// or at Stripe's page and back — «Invoice paid: … is up to date again».
// clock: data only — no code under test compares these dates with now.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';
import { defineComponent } from 'vue';

import { invoicePage, invoiceRow, unpaidRow } from './__tests__/billing-fixtures';
import { businessPage, businessRow, PLAZA, SALON } from './__tests__/fixtures';
import { describeCall, flush, mountBilling, type StreamCall } from './__tests__/mount-billing';
import { LIVE_TIMEOUT_MS } from '../../frontend/live-state';
import { errorFrame, HELLO, resultFrame } from '../../hubs/frontend/__tests__/mount-hubs';
import { PAYING_STORAGE_KEY } from './pay';
import { useUnpaidInvoices } from './unpaid';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  sessionStorage.clear();
  document.body.innerHTML = '';
});

const NORTE = businessRow('norte', 'Bar Norte', { status: 'suspended', unpaid_since: '2026-10-02T08:00:00Z' });
const OPEN_PLAZA = unpaidRow('i1', { total_cents: 3629 });
const OPEN_NORTE = unpaidRow('i2', { business: { id: 'norte', name: 'Bar Norte' }, date: '2026-10-02', total_cents: 4900 });

async function setup(api: (call: ReturnType<typeof describeCall>) => Response = () => Response.json({})) {
  let unpaid!: ReturnType<typeof useUnpaidInvoices>;
  const Host = defineComponent({
    setup() {
      unpaid = useUnpaidInvoices();
      return () => null;
    },
  });
  const s = await mountBilling(Host, { api: (call) => api(describeCall(call)) });
  const call: StreamCall = await s.live();
  const push = async (op: string, data: unknown, rev = 1) => {
    call.push(resultFrame(s.client.stream.subscriptions(op as never)[0].id, data, rev));
    await flush();
  };
  const show = async (open: unknown[], businesses = [PLAZA, NORTE, SALON], rev = 1) => {
    await push('hubs.business.list', businessPage(businesses), rev);
    await push('billing.invoice.list', invoicePage(open as never), rev);
  };
  const ids = () => unpaid.items.value?.map((item) => [item.business.id, item.invoice?.id ?? null]);
  return { ...s, call, push, show, ids, unpaid: () => unpaid };
}

describe('useUnpaidInvoices', () => {
  it('follows the account’s invoices not collected and its businesses', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('billing.invoice.list').map((sub) => sub.params)).toEqual([{ status: 'open', limit: 100 }]);
    expect(s.client.stream.subscriptions('hubs.business.list').map((sub) => sub.params)).toEqual([{ limit: 100 }]);
  });

  it('one item per business with an unpaid invoice, payment pending or suspended, with its invoice', async () => {
    const s = await setup();
    await s.show([OPEN_PLAZA, OPEN_NORTE]);
    expect(s.ids()).toEqual([
      ['plaza', 'i1'],
      ['norte', 'i2'],
    ]);
    expect(s.unpaid().items.value?.[0].business).toEqual(PLAZA);
  });

  it('two invoices of one business: the oldest, the one its grace counts from', async () => {
    const s = await setup();
    await s.show([unpaidRow('i3', { date: '2026-10-20' }), OPEN_PLAZA, unpaidRow('i4', { date: '2026-10-15' })], [PLAZA]);
    expect(s.ids()).toEqual([['plaza', 'i1']]);
  });

  it('a credit note is no debt, and a business the account does not see the invoice of goes without one', async () => {
    const s = await setup();
    await s.show([unpaidRow('c1', { kind: 'credit_note', business: { id: 'norte', name: 'Bar Norte' } })], [NORTE]);
    expect(s.ids()).toEqual([['norte', null]]);
  });

  it('nothing owed: an empty list, never a business that is up to date', async () => {
    const s = await setup();
    await s.show([], [SALON]);
    expect(s.unpaid().items.value).toEqual([]);
  });

  it('nothing until both lists answered', async () => {
    const s = await setup();
    await s.push('hubs.business.list', businessPage([PLAZA]));
    expect(s.unpaid().items.value).toBeUndefined();
    expect(s.unpaid().state.loading.value).toBe(true);
    await s.push('billing.invoice.list', invoicePage([OPEN_PLAZA]));
    expect(s.ids()).toEqual([['plaza', 'i1']]);
  });
});

describe('useUnpaidInvoices: lists that do not load are never read as «nothing owed»', () => {
  it.each(['billing.invoice.list', 'hubs.business.list'])('%s fails: it could not check', async (op) => {
    const s = await setup();
    s.call.push(errorFrame(s.client.stream.subscriptions(op as never)[0].id, 'internal_error'));
    await flush();
    expect(s.unpaid().state.failed.value).toBe(true);
    expect(s.unpaid().items.value).toBeUndefined();
  });

  it('nothing in time: the same, not silence', async () => {
    const s = await setup();
    await s.clock.advance(LIVE_TIMEOUT_MS - 1 - s.clock.now());
    expect(s.unpaid().state.failed.value).toBe(false);
    await s.clock.advance(1);
    expect(s.unpaid().state.failed.value).toBe(true);
  });

  it('«Retry» opens the stream again, once, and the items come', async () => {
    const s = await setup();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    s.unpaid().state.retry();
    await flush();
    await s.clock.advance(150);
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.unpaid().state.failed.value).toBe(false);
    const again = s.net.lastStream();
    again.push(HELLO);
    again.push(resultFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, businessPage([PLAZA]), 1));
    again.push(resultFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, invoicePage([OPEN_PLAZA]), 1));
    await flush();
    expect(s.ids()).toEqual([['plaza', 'i1']]);
  });
});

describe('useUnpaidInvoices: «Invoice paid»', () => {
  const paid = () => Response.json(invoiceRow('i1', { business: { id: 'plaza', name: 'Bar La Plaza' } }));

  it('an invoice that leaves the list because it was paid: «Invoice paid», once', async () => {
    const s = await setup((call) => (call.path === '/api/billing/invoices/detail' ? paid() : Response.json({})));
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
    const s = await setup(() => Response.json(invoiceRow('i1', { payment_status: 'void', payment_status_label: 'Void' })));
    await s.show([OPEN_PLAZA]);
    await s.show([], [PLAZA], 2);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('back from Stripe’s page with the invoice already paid: «Invoice paid», and it is forgotten', async () => {
    sessionStorage.setItem(PAYING_STORAGE_KEY, 'i1');
    const s = await setup(paid);
    await s.show([]);
    expect(toastSuccess).toHaveBeenCalledExactlyOnceWith('Invoice paid: Bar La Plaza is up to date again');
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBeNull();
  });

  it('back from Stripe’s page before the payment landed: said when it lands', async () => {
    sessionStorage.setItem(PAYING_STORAGE_KEY, 'i1');
    const s = await setup(paid);
    await s.show([OPEN_PLAZA]);
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBe('i1');
    await s.show([], [PLAZA], 2);
    expect(toastSuccess).toHaveBeenCalledExactlyOnceWith('Invoice paid: Bar La Plaza is up to date again');
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBeNull();
  });
});
