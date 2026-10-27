// Billing → Invoices (mockups `billing.html` «default», «selected», «empty», «loading», «error»; README §3b;
// UX-AUDIT-4 W-F9, W-F15, V-34): ERPlora's invoices of all the account's businesses in a server-side
// DataTable (live `billing.invoice.list`), cards up to 1100 px — invoice, date, business, amount, status —
// with filters by business (also `?business=`), status and year, a search by number, «Pay» on the web for
// one not collected (fixed, labelled; disabled while «Pay» waits), its PDF once issued (until then it reads
// «Issuing»), a selection with «Download PDF (n)», and «Download Excel» with what the filters show.
import { DataTable } from '@erplora/ui/components';
import { applySurface } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastInfo: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastInfo } from '@erplora/ui/shell';

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { mockResizeObserver } from '../../../packages/ui/src/components/DataTable/__tests__/harness';
import { errorFrame, HELLO, resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
import { invoicePage, invoiceRow, unpaidRow } from '../__tests__/billing-fixtures';
import { BAKERY, businessPage, businessRow, CAFE, PLAZA } from '../__tests__/fixtures';
import { accessibleName, describeCall, flush, mountBilling, optionValue, type StreamCall } from '../__tests__/mount-billing';
import { browser } from '../browser';
import InvoicesTab from './InvoicesTab.vue';

/** A desk wider than the table's card breakpoint (1100 px): the list, not the cards. */
const DESK = { width: 1440, height: 900 };
const viewport = (size: { width: number; height: number }) =>
  (window as unknown as { happyDOM: { setViewport(v: { width: number; height: number }): void } }).happyDOM.setViewport(size);

beforeEach(() => viewport(DESK));

afterEach(() => {
  viewport({ width: 1024, height: 768 });
  applySurface('web');
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.mocked(toastInfo).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

const PAID = invoiceRow('00123', { business: { id: 'bakery', name: 'Panadería López' }, date: '2026-10-01' });
const ISSUING = invoiceRow('00124', {
  business: { id: 'bakery', name: 'Panadería López' },
  fiscal_status: 'issuing',
  fiscal_status_label: 'Issuing',
  actions: [],
  can: { pay: false, pdf: false },
});
const OPEN = unpaidRow('i9', { reference: 'A1B2-0004' });
const ROWS = [OPEN, ISSUING, PAID];
/** A business the account works in but neither owns nor pays: its invoices are not the account's. */
const SALON = businessRow('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager', is_payer: false });

async function setup(path = '/dashboard/billing/invoices', api: (call: ReturnType<typeof describeCall>) => Response = () => Response.json({}), locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(InvoicesTab, { path, locale, api: (call) => api(describeCall(call)) });
  const call: StreamCall = await s.live();
  const push = async (op: string, data: unknown, rev = 1) => {
    call.push(resultFrame(s.client.stream.subscriptions(op as never)[0].id, data, rev));
    await flush();
  };
  const table = () => s.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const params = () => s.client.stream.subscriptions('billing.invoice.list').map((sub) => sub.params);
  const testid = (id: string) => s.wrapper.find(`[data-testid="${id}"]`);
  const show = async (rows = ROWS, businesses = [BAKERY, CAFE, PLAZA, SALON], rev = 1, extra: Record<string, unknown> = {}) => {
    await push('hubs.business.list', businessPage(businesses), rev);
    await push('billing.invoice.list', invoicePage(rows, extra), rev);
  };
  const change = async (id: string, value: unknown) => {
    testid(id).element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  };
  const openFilters = async () => {
    await testid('invoices-filters').trigger('click');
    await flush();
  };
  /** The table's search, as the person types it (`v-model:search`). */
  const query = {
    set value(text: string) {
      const bar = testid('invoices-search').element as HTMLElement & { value?: string };
      bar.value = text;
      bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
    },
  };
  return { ...s, call, push, table, prop, params, testid, show, change, openFilters, query };
}

describe('InvoicesTab: the list', () => {
  // BILLING-F22 (the trap of saas#58): one page of `billing.invoice.list` holds 100 rows at most; on a phone
  // «Load more» never asks for more, and past them the table pages instead (`maxWindow`).
  it('on a phone «Load more» grows one window from the first row, never past the server’s 100 rows', async () => {
    const s = await setup();
    await s.show(ROWS, undefined, 1, { total: 260 });
    expect(s.prop('maxWindow')).toBe(100);
    s.table().vm.$emit('loadMore');
    await flush();
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
    for (let n = 0; n < 4; n += 1) s.table().vm.$emit('loadMore');
    await flush();
    expect(s.params()).toEqual([{ limit: 100, offset: 0 }]);
  });

  it('follows the account’s invoices, the newest first, a page at a time', async () => {
    const s = await setup();
    expect(s.params()).toEqual([{ limit: 25, offset: 0 }]);
    await s.show();
    expect(s.table().props()).toMatchObject({
      serverSide: true,
      title: 'ERPlora invoices',
      total: 3,
      selectable: true,
      views: ['table', 'cards'],
      cardBreakpoint: 1100,
      searchable: true,
      searchPlaceholder: 'Search by number',
      testid: 'invoices',
      // A card's title is its number: the body does not repeat it («Invoice ERP-2026-00123», audit 2 R-30).
      cardTitleColumn: 'number',
    });
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Invoice', 'Date', 'Business', 'Amount', 'Status']);
    expect((s.prop<(n: number) => string>('entityLabel'))(1)).toBe('invoice');
    expect((s.prop<(n: number) => string>('entityLabel'))(12)).toBe('invoices');
  });

  it('names each invoice by its number (Stripe’s reference until it is paid), with its date, business, amount and status', async () => {
    const s = await setup();
    await s.show();
    const rows = s.wrapper.findAll('[data-testid="invoices-row"]');
    expect(rows.map((row) => row.findAll('[role="cell"]').map((cell) => cell.text()).slice(0, 5))).toEqual([
      ['A1B2-0004', 'Oct 10, 2026', 'Bar La Plaza', '€36.29', 'Not collected'],
      ['ERP-2026-00124', 'Oct 1, 2026', 'Panadería López', '€36.29', 'Issuing'],
      ['ERP-2026-00123', 'Oct 1, 2026', 'Panadería López', '€36.29', 'Paid'],
    ]);
  });

  it('a credit note says so under its number, and links to the invoice it rectifies', async () => {
    const s = await setup('/dashboard/billing/invoices', (call) =>
      call.path === '/api/billing/invoices/detail' ? Response.json({ ...invoiceRow(call.query.id), rectifies: { id: '00123', number: 'ERP-2026-00123' } }) : Response.json({}),
    );
    await s.show([PAID, invoiceRow('c1', { kind: 'credit_note', kind_label: 'Credit note', number: 'ERPR-2026-00001', total_cents: -3629 })]);
    // Only the credit note is asked for what it rectifies (`billing.invoice.get`), once.
    expect(s.calls().filter((c) => c.path === '/api/billing/invoices/detail')).toEqual([
      { method: 'GET', path: '/api/billing/invoices/detail', body: undefined, query: { id: 'c1' } },
    ]);
    const cell = s.wrapper.get('[data-testid="invoices-row"][data-id="c1"]').findAll('[role="cell"]')[0];
    expect(cell.get('[data-testid="invoice-kind"]').text()).toBe('Credit note');
    const link = cell.get('[data-testid="invoice-rectifies"]');
    expect(link.text()).toBe('Rectifies ERP-2026-00123');
    await link.trigger('click');
    await flush();
    expect(s.params()).toEqual([{ search: 'ERP-2026-00123', limit: 25, offset: 0 }]);
    await s.show([PAID, invoiceRow('c1', { kind: 'credit_note', kind_label: 'Credit note', number: 'ERPR-2026-00001' })], [BAKERY], 2);
    expect(s.calls().filter((c) => c.path === '/api/billing/invoices/detail')).toHaveLength(1);
  });

  it('a credit note says its VeriFactu type and why next to what it rectifies (R1 · reason), in each language', async () => {
    const credit = invoiceRow('c1', {
      kind: 'credit_note',
      kind_label: 'Credit note',
      number: 'ERPR-2026-00001',
      total_cents: -3629,
      rectification: { type: 'R1', reason: 'Duplicate charge' },
      stripe_source_id: 'cn_1',
    });
    const noReason = invoiceRow('c2', {
      kind: 'credit_note',
      kind_label: 'Credit note',
      number: 'ERPR-2026-00002',
      rectification: { type: 'R4', reason: '' },
      stripe_source_id: 're_1',
    });
    const detail = (call: ReturnType<typeof describeCall>) =>
      call.path === '/api/billing/invoices/detail' ? Response.json({ ...invoiceRow(call.query.id), rectifies: { id: '00123', number: 'ERP-2026-00123' } }) : Response.json({});
    const cell = (s: Awaited<ReturnType<typeof setup>>, id: string) =>
      s.wrapper.get(`[data-testid="invoices-row"][data-id="${id}"]`).findAll('[role="cell"]')[0];

    const en = await setup('/dashboard/billing/invoices', detail);
    await en.show([PAID, credit, noReason]);
    expect(cell(en, 'c1').get('[data-testid="invoice-kind"]').text()).toBe('Credit note R1 · Duplicate charge');
    expect(cell(en, 'c1').get('[data-testid="invoice-kind"]').attributes('title')).toBe('Credit note R1 · Duplicate charge');
    expect(cell(en, 'c1').get('[data-testid="invoice-rectifies"]').text()).toBe('Rectifies ERP-2026-00123');
    expect(cell(en, 'c2').get('[data-testid="invoice-kind"]').text()).toBe('Credit note R4');
    // An invoice is no rectification: nothing under its number.
    expect(cell(en, '00123').find('[data-testid="invoice-kind"]').exists()).toBe(false);
    en.wrapper.unmount();

    const es = await setup('/dashboard/billing/invoices', detail, 'es');
    await es.show([PAID, credit]);
    expect(cell(es, 'c1').get('[data-testid="invoice-kind"]').text()).toBe('Rectificativa R1 · Duplicate charge');
    expect(cell(es, 'c1').get('[data-testid="invoice-rectifies"]').text()).toBe('Rectifica ERP-2026-00123');
  });

  it('per row, «Pay» (fixed and labelled) for one not collected, the PDF once issued and «View invoice» (BILLING-G92)', async () => {
    const s = await setup();
    await s.show();
    const actions = s.prop<Array<Record<string, unknown>>>('actions');
    expect(actions.map((a) => [a.id, !!a.pinned, !!a.showLabel])).toEqual([
      ['pay', true, true],
      ['pdf', false, false],
      ['view', false, false],
    ]);
    const ids = (row: string) => s.wrapper.findAll(`[data-testid^="invoices-row-${row}-"]`).map((b) => b.attributes('data-testid')!.split('-').pop());
    expect(ids('i9')).toEqual(['pay', 'view']);
    expect(ids('00124')).toEqual(['view']);
    expect(ids('00123')).toEqual(['pdf', 'view']);
    expect(s.testid('invoices-row-i9-pay').text()).toBe('Pay');
  });

  it('BILLING-G05: «View invoice» opens the page of that invoice', async () => {
    const s = await setup();
    await s.show();
    await s.testid('invoices-row-00123-view').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/dashboard/billing/invoices/00123');
  });

  it('«Pay» goes to Stripe’s page of that invoice', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup('/dashboard/billing/invoices', (call) => (call.path === '/api/billing/invoices/pay' ? Response.json({ url: 'https://invoice.stripe.com/i/x' }) : Response.json({})));
    await s.show();
    await s.testid('invoices-row-i9-pay').trigger('click');
    await flush();
    expect(s.calls().filter((c) => c.method === 'POST')).toEqual([{ method: 'POST', path: '/api/billing/invoices/pay', body: { id: 'i9' }, query: {} }]);
    expect(assign).toHaveBeenCalledWith('https://invoice.stripe.com/i/x');
  });

  it('«Pay» stays disabled while it waits for another card', async () => {
    const s = await setup();
    await s.show([unpaidRow('i9', { pay_blocked_reason: 'card_change_required', can: { pay: false, pdf: false } })]);
    expect((s.testid('invoices-row-i9-pay').element as HTMLElement & { disabled: boolean }).disabled).toBe(true);
  });

  it('the PDF downloads the file the platform hub issued', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup();
    await s.show();
    await s.testid('invoices-row-00123-pdf').trigger('click');
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/pdf?id=00123', 'application/pdf');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('on the %s surface the invoices are there, «Pay» is not', async (surface) => {
    applySurface(surface);
    const s = await setup();
    await s.show();
    expect(s.wrapper.findAll('[data-testid="invoices-row"]')).toHaveLength(3);
    expect(s.testid('invoices-row-i9-pay').exists()).toBe(false);
    expect(s.testid('invoices-row-00123-pdf').exists()).toBe(true);
  });

  it('loading, it says so; failing, it says why and retries', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    s.call.push(`event: error\ndata: ${JSON.stringify({ id: s.client.stream.subscriptions('billing.invoice.list')[0].id, error: { code: 'internal', message: 'Something failed.' } })}\n\n`);
    await flush();
    expect(s.prop('error')).toBe('Something failed.');
    expect(s.prop<Record<string, string>>('labels')).toMatchObject({ loadError: 'We could not load your invoices', retry: 'Retry' });
  });
});

describe('InvoicesTab: a list that does not load says so, never «No invoices yet» (audit 2026-10-14, R-04)', () => {
  const failed = (s: Awaited<ReturnType<typeof setup>>) => ({
    error: s.prop<string | undefined>('error'),
    loading: s.prop<boolean>('loading'),
    retry: s.testid('invoices-retry').exists(),
    empty: s.testid('invoices-empty').exists(),
  });

  it('a query that fails: the reason and «Retry», not the empty state', async () => {
    const s = await setup();
    await s.push('hubs.business.list', businessPage([BAKERY]));
    s.call.push(errorFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, 'internal_error'));
    await flush();
    expect(failed(s)).toEqual({ error: 'msg internal_error', loading: false, retry: true, empty: false });
  });

  it('nothing in time: an error with «Retry», never a spinner for ever', async () => {
    const s = await setup();
    await s.push('hubs.business.list', businessPage([BAKERY]));
    // The time limit counts from the mount (opening the stream already took 150 ms of it).
    await s.clock.advance(LIVE_TIMEOUT_MS - 1 - s.clock.now());
    expect(s.prop('loading')).toBe(true);
    await s.clock.advance(1);
    expect(failed(s)).toEqual({ error: 'Check your connection and try again.', loading: false, retry: true, empty: false });
  });

  it('the stream refused (/api/live answers 503): it could not load, it does not say there are no invoices', async () => {
    const s = await mountBilling(InvoicesTab, { path: '/dashboard/billing/invoices' });
    s.liveDown.value = true;
    await s.clock.advance(150);
    expect(s.client.stream.subscriptions('billing.invoice.list')).toHaveLength(1);
    expect(s.wrapper.find('[data-testid="invoices-retry"]').exists()).toBe(true);
    expect(s.wrapper.find('[data-testid="invoices-empty"]').exists()).toBe(false);
    expect(s.wrapper.find('[data-testid="invoices-loading"]').exists()).toBe(false);
  });

  it('«Retry» opens the stream again and shows the invoices that come', async () => {
    const s = await setup();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    await s.testid('invoices-retry').trigger('click');
    await flush();
    await s.clock.advance(150);
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.prop('loading')).toBe(true);
    const again = s.net.lastStream();
    again.push(HELLO);
    again.push(resultFrame(s.client.stream.subscriptions('billing.invoice.list')[0].id, invoicePage(ROWS), 1));
    await flush();
    expect(s.wrapper.findAll('[data-testid="invoices-row"]')).toHaveLength(3);
    expect(s.prop('error')).toBeUndefined();
  });

  it('the businesses (only the filter’s options) failing do not block the invoices', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.client.stream.subscriptions('hubs.business.list')[0].id, 'internal_error'));
    await s.push('billing.invoice.list', invoicePage(ROWS));
    expect(s.wrapper.findAll('[data-testid="invoices-row"]')).toHaveLength(3);
    expect(s.prop('error')).toBeUndefined();
  });

  it('says it in Spanish', async () => {
    const s = await setup('/dashboard/billing/invoices', undefined, 'es');
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.prop('error')).toBe('Comprueba tu conexión y vuelve a intentarlo.');
    expect(s.prop<Record<string, string>>('labels')).toMatchObject({ loadError: 'No hemos podido cargar tus facturas', retry: 'Reintentar' });
  });
});

describe('InvoicesTab: a clean page (Ioan, 2026-10-14)', () => {
  it('the list fills the page between the topbar and the tabbar: a `.panel-fill` stack, the table with `fill`', async () => {
    const s = await setup();
    await s.show();
    expect(s.prop('fill')).toBe(true);
    expect(s.wrapper.element.classList.contains('panel-fill')).toBe(true);
    expect(s.table().element.parentElement).toBe(s.wrapper.element);
  });

  it('the toolbar holds one «Filters» control and asks for rows per page only past the shortest page', async () => {
    const s = await setup();
    await s.show();
    expect(s.wrapper.findAll('.data-table__bar-main > ion-select[data-testid^="invoices-"]')).toHaveLength(0);
    expect(s.testid('invoices-filters').exists()).toBe(true);
    expect(s.prop('pageSizeChooser')).toBe(false);
    await s.show(ROWS, undefined, 2, { total: 26 });
    expect(s.prop('pageSizeChooser')).toBe(true);
  });
});

describe('InvoicesTab: filters and search', () => {
  it('filters by business (the ones the account owns or pays), status and year, from one «Filters» control', async () => {
    const s = await setup();
    await s.show();
    // One control in the toolbar (Ioan, 2026-10-14): the filters live in its popover.
    expect(s.testid('invoices-business').exists()).toBe(false);
    await s.openFilters();
    expect(s.testid('invoices-business').findAll('ion-select-option').map((o) => [optionValue(o), o.text()])).toEqual([
      ['', 'All businesses'],
      ['plaza', 'Bar La Plaza'],
      ['cafe', 'Café Central'],
      ['bakery', 'Panadería López'],
    ]);
    expect(s.testid('invoices-status').findAll('ion-segment-button').map((b) => b.text())).toEqual(['All', 'Paid', 'Not collected']);
    expect(s.testid('invoices-year').findAll('ion-select-option').map((o) => o.text())[0]).toBe('All years');
    await s.change('invoices-business', 'bakery');
    await s.change('invoices-status', 'paid');
    await s.change('invoices-year', 2026);
    expect(s.router.currentRoute.value.query).toEqual({ business: 'bakery', status: 'paid', year: '2026' });
    expect(s.params()).toEqual([{ hub_id: 'bakery', status: 'paid', year: 2026, limit: 25, offset: 0 }]);
    expect(s.testid('invoices-filters-count').text()).toBe('3');
    await s.change('invoices-business', '');
    expect(s.router.currentRoute.value.query).toEqual({ status: 'paid', year: '2026' });
    await s.change('invoices-status', 'all');
    expect(s.router.currentRoute.value.query).toEqual({ year: '2026' });
  });

  it('«Clear filters» drops the business, the status and the year, and keeps the search', async () => {
    const s = await setup('/dashboard/billing/invoices?business=plaza&status=open&year=2026');
    await s.show([OPEN]);
    s.query.value = '0004';
    await s.openFilters();
    await s.testid('invoices-filters-clear').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.query).toEqual({});
    expect(s.params().at(-1)).toEqual({ search: '0004', limit: 25, offset: 0 });
  });

  it('opens on the business of the address (`?business=`), with its status', async () => {
    const s = await setup('/dashboard/billing/invoices?business=plaza&status=open');
    expect(s.params()).toEqual([{ hub_id: 'plaza', status: 'open', limit: 25, offset: 0 }]);
    await s.show([OPEN]);
    await s.openFilters();
    expect((s.testid('invoices-business').element as HTMLElement & { value: unknown }).value).toBe('plaza');
    expect((s.testid('invoices-status').element as HTMLElement & { value: unknown }).value).toBe('open');
    expect(s.testid('invoices-unknown-business').exists()).toBe(false);
  });

  it('a business of the address that is not the account’s: every invoice, saying so', async () => {
    const s = await setup('/dashboard/billing/invoices?business=xyz');
    await s.show();
    expect(s.testid('invoices-unknown-business').text()).toBe('We could not find that business among yours: here are the invoices of all of them.');
    expect(s.params()).toEqual([{ limit: 25, offset: 0 }]);
  });

  it('searches by number on the server, from the first page', async () => {
    const s = await setup();
    await s.show();
    const bar = s.testid('invoices-search').element as HTMLElement & { value?: string };
    bar.value = '0012';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: '0012' } }));
    await flush();
    expect(s.params()).toEqual([{ search: '0012', limit: 25, offset: 0 }]);
  });

  it('«Download Excel» downloads what the filters show', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup('/dashboard/billing/invoices?business=bakery&year=2026');
    await s.show([PAID]);
    const csv = s.testid('invoices-csv');
    // On a phone it reads «Excel» (the toolbar stays on two lines); its name is the whole one everywhere.
    expect(csv.get('.csv-label--long').text()).toBe('Download Excel');
    expect(csv.get('.csv-label--short').text()).toBe('Excel');
    expect(accessibleName(csv)).toBe('Download Excel');
    expect(csv.attributes('title')).toBe('The list of what the filters show, for your accountant (it opens in Excel)');
    await csv.trigger('click');
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/csv?hub_id=bakery&year=2026', 'text/csv');
  });
});

describe('InvoicesTab: the toolbar on one line from 641 px (audit 2026-10-14, R-14)', () => {
  /** A fake layout of the toolbar: the first item on line 1; «Download Excel» on line `csvLine`. */
  function layOut(csvLine: () => 1 | 2) {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
      const isCsv = this.getAttribute('data-testid') === 'invoices-csv';
      const top = isCsv ? (csvLine() === 1 ? 2 : 44) : 0;
      const height = isCsv ? 32 : 36;
      return { top, bottom: top + height, height, left: 0, right: 0, width: 0, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
    });
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(760);
  }

  it('when «Download Excel» falls to a second line, it folds to its icon, still named «Download Excel»', async () => {
    const observers = mockResizeObserver();
    let line: 1 | 2 = 1;
    layOut(() => line);
    const s = await setup('/dashboard/billing/invoices?year=2026');
    await s.show([PAID]);
    observers.fire();
    await flush();
    expect(s.wrapper.classes()).not.toContain('invoices--compact');
    line = 2;
    observers.fire();
    await flush();
    expect(s.wrapper.classes()).toContain('invoices--compact');
    const csv = s.testid('invoices-csv');
    expect(accessibleName(csv)).toBe('Download Excel');
    expect(csv.attributes('title')).toBe('The list of what the filters show, for your accountant (it opens in Excel)');
    expect(csv.get('ion-icon').attributes('aria-hidden')).toBe('true');
  });

  it('a selection that comes or goes tries the full toolbar again', async () => {
    const observers = mockResizeObserver();
    let line: 1 | 2 = 2;
    layOut(() => line);
    const s = await setup('/dashboard/billing/invoices?year=2026');
    await s.show([PAID]);
    observers.fire();
    await flush();
    expect(s.wrapper.classes()).toContain('invoices--compact');
    line = 1;
    s.table().vm.$emit('update:selected', ['00123']);
    await flush();
    expect(s.wrapper.classes()).not.toContain('invoices--compact');
  });
});

describe('InvoicesTab: selection', () => {
  // Audit 2 S-01: «Download PDF (n)» counts only the issued ones; what has no PDF yet is said above the list,
  // unpaid apart («still being issued» was false for an invoice that is not paid).
  it('«Download PDF (n)» counts and downloads the selected ones issued; the others are said above the list', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup();
    await s.show();
    expect(s.testid('invoices-pdf-selected').exists()).toBe(false);
    s.table().vm.$emit('update:selected', ['00123', '00124']);
    await flush();
    const button = s.testid('invoices-pdf-selected');
    expect(button.text()).toBe('Download PDF (1)');
    expect(s.testid('invoices-selection-note').text()).toBe('1 selected invoice is still being issued: its PDF is ready in a few minutes.');
    await button.trigger('click');
    await flush();
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/pdf?id=00123', 'application/pdf');
    expect(toastInfo).not.toHaveBeenCalled();
  });

  it('unpaid invoices have no PDF: they are not counted, and the note says why (audit 2 S-01)', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup();
    await s.show([OPEN, unpaidRow('i10'), PAID]);
    s.table().vm.$emit('update:selected', ['i9', 'i10', '00123']);
    await flush();
    expect(s.testid('invoices-pdf-selected').text()).toBe('Download PDF (1)');
    expect(s.testid('invoices-selection-note').text()).toBe('2 selected invoices are unpaid: an unpaid invoice has no PDF until it is paid.');
    await s.testid('invoices-pdf-selected').trigger('click');
    await flush();
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/pdf?id=00123', 'application/pdf');
    expect(toastInfo).not.toHaveBeenCalled();
  });

  it('only unpaid ones selected: «Download PDF (0)» is disabled, described by the reason', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup();
    await s.show([OPEN, PAID]);
    s.table().vm.$emit('update:selected', ['i9']);
    await flush();
    const button = s.testid('invoices-pdf-selected');
    expect(button.text()).toBe('Download PDF (0)');
    expect((button.element as HTMLElement & { disabled: boolean }).disabled).toBe(true);
    const note = s.testid('invoices-selection-note');
    expect(note.text()).toBe('1 selected invoice is unpaid: an unpaid invoice has no PDF until it is paid.');
    // Ionic hands the host's aria-* to its native button.
    const native = button.element.shadowRoot?.querySelector('button');
    expect(native?.getAttribute('aria-describedby') ?? button.attributes('aria-describedby')).toBe(note.attributes('id'));
    await button.trigger('click');
    await flush();
    expect(download).not.toHaveBeenCalled();
  });

  it('says it in Spanish', async () => {
    const s = await setup('/dashboard/billing/invoices', undefined, 'es');
    await s.show([OPEN, PAID]);
    s.table().vm.$emit('update:selected', ['i9', '00123']);
    await flush();
    expect(s.testid('invoices-pdf-selected').text()).toBe('Descargar PDF (1)');
    expect(s.testid('invoices-selection-note').text()).toBe('1 factura seleccionada está sin pagar: una factura sin pagar no tiene PDF hasta que se paga.');
  });

  it('keeps the rows selected on another page', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup();
    await s.show([PAID], [BAKERY], 1, { total: 30 });
    s.table().vm.$emit('update:selected', ['00123']);
    await flush();
    await s.show([invoiceRow('00200')], [BAKERY], 2, { total: 30, offset: 25 });
    s.table().vm.$emit('update:selected', ['00123', '00200']);
    await flush();
    await s.testid('invoices-pdf-selected').trigger('click');
    await flush();
    expect(download.mock.calls.map(([url]) => url)).toEqual(['/api/billing/invoices/pdf?id=00123', '/api/billing/invoices/pdf?id=00200']);
  });
});

describe('InvoicesTab: a file is saved only when it is the file (audit 2026-10-14, R-05)', () => {
  /** The browser's network for the files: one answer per path; what was asked, kept. */
  function serveFiles(answer: (url: string) => Response) {
    const asked: string[] = [];
    vi.stubGlobal('fetch', (url: string) => {
      asked.push(url);
      return Promise.resolve(answer(url));
    });
    return asked;
  }
  /** What reaches the disk: an object URL made for a blob and an anchor clicked. */
  function watchSaves() {
    const saved: string[] = [];
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:http://localhost/1');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.getAttribute('download') ?? '');
    });
    return saved;
  }
  const envelope = (status: number, code: string, message: string) => Response.json({ error: { code, message } }, { status });
  const pdfAction = (s: Awaited<ReturnType<typeof setup>>, id = '00123') => s.testid(`invoices-row-${id}-pdf`).element as HTMLElement & { disabled: boolean };
  const press = async (s: Awaited<ReturnType<typeof setup>>, id: string) => {
    await s.testid(id).trigger('click');
    await flush();
  };

  it('a PDF the platform hub issued is saved under its name', async () => {
    const asked = serveFiles(
      () =>
        new Response('%PDF-1.7', {
          status: 200,
          headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="ERP-2026-00123.pdf"' },
        }),
    );
    const saved = watchSaves();
    const s = await setup();
    await s.show();
    await press(s, 'invoices-row-00123-pdf');
    expect(asked).toEqual(['/api/billing/invoices/pdf?id=00123']);
    expect(saved).toEqual(['ERP-2026-00123.pdf']);
    expect(toastInfo).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('one still being issued (404): says so, saves nothing, and its PDF waits', async () => {
    serveFiles(() => envelope(404, 'billing.invoice_not_issued', 'This invoice is still being issued: its PDF is ready once it is.'));
    const saved = watchSaves();
    const s = await setup();
    await s.show();
    expect(pdfAction(s).disabled).toBe(false);
    await press(s, 'invoices-row-00123-pdf');
    expect(saved).toEqual([]);
    expect(toastInfo).toHaveBeenCalledExactlyOnceWith('This invoice is still being issued: its PDF will be ready as soon as it finishes.');
    expect(pdfAction(s).disabled).toBe(true);
  });

  it('its PDF waits until its row changes in the list (the server issued it again, or says more)', async () => {
    serveFiles(() => envelope(404, 'billing.invoice_not_issued', 'This invoice is still being issued: its PDF is ready once it is.'));
    watchSaves();
    const s = await setup();
    await s.show();
    await press(s, 'invoices-row-00123-pdf');
    expect(pdfAction(s).disabled).toBe(true);
    // Another row changes: this one still waits.
    await s.show([unpaidRow('i9', { total_cents: 100 }), ISSUING, PAID], undefined, 2);
    expect(pdfAction(s).disabled).toBe(true);
    await s.show([OPEN, ISSUING, { ...PAID, fiscal_status_label: 'Accepted with errors', fiscal_status: 'accepted_with_errors' }], undefined, 3);
    expect(pdfAction(s).disabled).toBe(false);
  });

  it('the invoice service down (503): says it, saves nothing, and the PDF can be asked again', async () => {
    serveFiles(() => envelope(503, 'billing.platform_unavailable', 'The invoice cannot be downloaded right now. Try again in a moment.'));
    const saved = watchSaves();
    const s = await setup();
    await s.show();
    await press(s, 'invoices-row-00123-pdf');
    expect(saved).toEqual([]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('The invoice service is not answering. Try again in a moment.');
    expect(pdfAction(s).disabled).toBe(false);
  });

  it('without network: the panel’s sentence for it', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    const saved = watchSaves();
    const s = await setup();
    await s.show();
    await press(s, 'invoices-row-00123-pdf');
    expect(saved).toEqual([]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('We could not reach ERPlora. Check your connection and try again.');
  });

  it('«Download Excel» that fails (503): says why and saves nothing', async () => {
    const asked = serveFiles(() => envelope(503, 'service_unavailable', 'The service is not available right now.'));
    const saved = watchSaves();
    const s = await setup('/dashboard/billing/invoices?year=2026');
    await s.show([PAID]);
    await press(s, 'invoices-csv');
    expect(asked).toEqual(['/api/billing/invoices/csv?year=2026']);
    expect(saved).toEqual([]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('The service is not available right now.');
  });

  it('«Download PDF (n)»: each file on its own; the ones the server says are still being issued counted once, and they wait', async () => {
    const asked = serveFiles((url) =>
      url.endsWith('00123')
        ? new Response('%PDF', { status: 200, headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="ERP-2026-00123.pdf"' } })
        : envelope(404, 'billing.invoice_not_issued', 'This invoice is still being issued: its PDF is ready once it is.'),
    );
    const saved = watchSaves();
    const s = await setup();
    await s.show([PAID, ISSUING, invoiceRow('00125'), invoiceRow('00126')]);
    s.table().vm.$emit('update:selected', ['00123', '00124', '00125', '00126']);
    await flush();
    await press(s, 'invoices-pdf-selected');
    // ISSUING (00124) has no PDF yet: the note says so and it is not asked for.
    expect(asked).toEqual(['/api/billing/invoices/pdf?id=00123', '/api/billing/invoices/pdf?id=00125', '/api/billing/invoices/pdf?id=00126']);
    expect(saved).toEqual(['ERP-2026-00123.pdf']);
    expect(toastInfo).toHaveBeenCalledExactlyOnceWith('2 invoices are still being issued: their PDF is ready in a few minutes.');
    expect(pdfAction(s, '00125').disabled).toBe(true);
    expect(pdfAction(s, '00123').disabled).toBe(false);
  });

  it('«Download PDF (n)» with the invoice service down: one error, not one per file', async () => {
    serveFiles(() => envelope(503, 'billing.platform_unavailable', 'The invoice cannot be downloaded right now. Try again in a moment.'));
    const saved = watchSaves();
    const s = await setup();
    await s.show([PAID, invoiceRow('00125')]);
    s.table().vm.$emit('update:selected', ['00123', '00125']);
    await flush();
    await press(s, 'invoices-pdf-selected');
    expect(saved).toEqual([]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('The invoice service is not answering. Try again in a moment.');
  });

  // One notice at a time (a new one closes the one on screen, as Material's snackbar): a failure and invoices still
  // being issued in the same download are said together, in the error, or the second notice would close the error.
  it('«Download PDF (n)» with one failing and others still being issued: one error notice that says both', async () => {
    serveFiles((url) =>
      url.endsWith('00123')
        ? envelope(503, 'billing.platform_unavailable', 'The invoice cannot be downloaded right now. Try again in a moment.')
        : envelope(404, 'billing.invoice_not_issued', 'This invoice is still being issued: its PDF is ready once it is.'),
    );
    const saved = watchSaves();
    const s = await setup();
    await s.show([PAID, ISSUING, invoiceRow('00125'), invoiceRow('00126')]);
    s.table().vm.$emit('update:selected', ['00123', '00124', '00125', '00126']);
    await flush();
    await press(s, 'invoices-pdf-selected');
    expect(saved).toEqual([]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith(
      'The invoice service is not answering. Try again in a moment. 2 invoices are still being issued: their PDF is ready in a few minutes.',
    );
    expect(toastInfo).not.toHaveBeenCalled();
  });

  it('one failing and one still being issued, said together in Spanish (in the singular)', async () => {
    serveFiles((url) =>
      url.endsWith('00123')
        ? envelope(503, 'billing.platform_unavailable', 'Ahora no se puede descargar la factura.')
        : envelope(404, 'billing.invoice_not_issued', 'Esta factura aún se está emitiendo.'),
    );
    watchSaves();
    const s = await setup('/dashboard/billing/invoices', undefined, 'es');
    await s.show([PAID, invoiceRow('00125')]);
    s.table().vm.$emit('update:selected', ['00123', '00125']);
    await flush();
    await press(s, 'invoices-pdf-selected');
    expect(toastError).toHaveBeenCalledExactlyOnceWith(
      'El servicio de facturas no responde. Prueba de nuevo en un momento. Esa factura aún se está emitiendo: su PDF estará en unos minutos.',
    );
    expect(toastInfo).not.toHaveBeenCalled();
  });

  // A notice is one line of text (Material's snackbar): its sentences one after the other, each with its stop, never a
  // line break (painted as a bare space) nor two sentences run together when the server's words end without one.
  it('what failed and what is still being issued read as two sentences on one line, even without the server’s stop', async () => {
    serveFiles((url) =>
      url.endsWith('00123')
        ? envelope(503, 'service_unavailable', 'The service is not available right now')
        : envelope(404, 'billing.invoice_not_issued', 'This invoice is still being issued: its PDF is ready once it is.'),
    );
    watchSaves();
    const s = await setup();
    await s.show([PAID, invoiceRow('00125')]);
    s.table().vm.$emit('update:selected', ['00123', '00125']);
    await flush();
    await press(s, 'invoices-pdf-selected');
    const said = String(vi.mocked(toastError).mock.calls[0]?.[0]);
    expect(said).not.toMatch(/\n/);
    expect(said).toBe('The service is not available right now. That invoice is still being issued: its PDF is ready in a few minutes.');
  });

  it('says it in Spanish', async () => {
    serveFiles((url) =>
      url.endsWith('00123')
        ? envelope(404, 'billing.invoice_not_issued', 'Esta factura aún se está emitiendo.')
        : envelope(503, 'billing.platform_unavailable', 'Ahora no se puede descargar la factura.'),
    );
    watchSaves();
    const s = await setup('/dashboard/billing/invoices', undefined, 'es');
    await s.show([PAID, invoiceRow('00125')]);
    await press(s, 'invoices-row-00123-pdf');
    expect(toastInfo).toHaveBeenCalledExactlyOnceWith('Esta factura se está emitiendo: su PDF estará listo en cuanto termine.');
    await press(s, 'invoices-row-00125-pdf');
    expect(toastError).toHaveBeenCalledExactlyOnceWith('El servicio de facturas no responde. Prueba de nuevo en un momento.');
  });
});

describe('InvoicesTab: empty', () => {
  it('without invoices it says why (Free charges nothing) and offers the plans on the web', async () => {
    const s = await setup();
    await s.show([]);
    expect(s.prop('hideToolbarWhenEmpty')).toBe(true);
    const empty = s.testid('invoices-empty');
    expect(empty.text()).toContain('No invoices yet');
    expect(empty.text()).toContain('On the Free plan nothing is charged, so there are no invoices. They appear here when you pay for a plan or a module.');
    expect(s.testid('invoices-empty-plans').attributes('routerlink')).toBe('/dashboard/store/plans');
  });

  it('inside the apps, the same without selling', async () => {
    applySurface('desktop');
    const s = await setup();
    await s.show([]);
    expect(s.testid('invoices-empty').text()).toContain('No invoices yet');
    expect(s.testid('invoices-empty-plans').exists()).toBe(false);
  });

  it('a business on Free says it has none', async () => {
    const s = await setup('/dashboard/billing/invoices?business=cafe');
    await s.show([]);
    expect(s.testid('invoices-empty').text()).toContain('Café Central is on Free: it has no invoices.');
  });

  it('filters that find nothing keep the toolbar and offer to show everything', async () => {
    const s = await setup('/dashboard/billing/invoices?status=open&year=2024');
    await s.show([]);
    expect(s.prop('hideToolbarWhenEmpty')).toBe(false);
    expect(s.testid('invoices-empty').text()).toContain('No invoice matches the search or the filters');
    await s.testid('invoices-show-all').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.query).toEqual({});
    expect(s.params()).toEqual([{ limit: 25, offset: 0 }]);
  });
});

describe('InvoicesTab: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup('/dashboard/billing/invoices', undefined, 'es');
    await s.show([OPEN]);
    expect(s.prop('title')).toBe('Facturas de ERPlora');
    expect(s.wrapper.get('[data-testid="invoices-row"]').findAll('[role="cell"]').map((c) => c.text()).slice(0, 5)).toEqual([
      'A1B2-0004',
      '10 oct 2026',
      'Bar La Plaza',
      '36,29 €',
      'No cobrada',
    ]);
    expect(s.testid('invoices-csv').get('.csv-label--long').text()).toBe('Descargar Excel');
    expect(s.testid('invoices-row-i9-pay').text()).toBe('Pagar');
  });
});

