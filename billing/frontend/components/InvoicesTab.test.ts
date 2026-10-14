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

import { toastInfo } from '@erplora/ui/shell';

import { resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
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
  vi.restoreAllMocks();
  vi.mocked(toastInfo).mockClear();
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

async function setup(path = '/billing/invoices', api: (call: ReturnType<typeof describeCall>) => Response = () => Response.json({}), locale: 'en' | 'es' = 'en') {
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
    const s = await setup('/billing/invoices', (call) =>
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

    const en = await setup('/billing/invoices', detail);
    await en.show([PAID, credit, noReason]);
    expect(cell(en, 'c1').get('[data-testid="invoice-kind"]').text()).toBe('Credit note R1 · Duplicate charge');
    expect(cell(en, 'c1').get('[data-testid="invoice-kind"]').attributes('title')).toBe('Credit note R1 · Duplicate charge');
    expect(cell(en, 'c1').get('[data-testid="invoice-rectifies"]').text()).toBe('Rectifies ERP-2026-00123');
    expect(cell(en, 'c2').get('[data-testid="invoice-kind"]').text()).toBe('Credit note R4');
    // An invoice is no rectification: nothing under its number.
    expect(cell(en, '00123').find('[data-testid="invoice-kind"]').exists()).toBe(false);
    en.wrapper.unmount();

    const es = await setup('/billing/invoices', detail, 'es');
    await es.show([PAID, credit]);
    expect(cell(es, 'c1').get('[data-testid="invoice-kind"]').text()).toBe('Rectificativa R1 · Duplicate charge');
    expect(cell(es, 'c1').get('[data-testid="invoice-rectifies"]').text()).toBe('Rectifica ERP-2026-00123');
  });

  it('per row, «Pay» (fixed and labelled) for one not collected and the PDF once issued', async () => {
    const s = await setup();
    await s.show();
    const actions = s.prop<Array<Record<string, unknown>>>('actions');
    expect(actions.map((a) => [a.id, !!a.pinned, !!a.showLabel])).toEqual([
      ['pay', true, true],
      ['pdf', false, false],
    ]);
    const ids = (row: string) => s.wrapper.findAll(`[data-testid^="invoices-row-${row}-"]`).map((b) => b.attributes('data-testid')!.split('-').pop());
    expect(ids('i9')).toEqual(['pay']);
    expect(ids('00124')).toEqual([]);
    expect(ids('00123')).toEqual(['pdf']);
    expect(s.testid('invoices-row-i9-pay').text()).toBe('Pay');
  });

  it('«Pay» goes to Stripe’s page of that invoice', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await setup('/billing/invoices', (call) => (call.path === '/api/billing/invoices/pay' ? Response.json({ url: 'https://invoice.stripe.com/i/x' }) : Response.json({})));
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
    const download = vi.spyOn(browser, 'download').mockImplementation(() => {});
    const s = await setup();
    await s.show();
    await s.testid('invoices-row-00123-pdf').trigger('click');
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/pdf?id=00123');
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
    const s = await setup('/billing/invoices?business=plaza&status=open&year=2026');
    await s.show([OPEN]);
    s.query.value = '0004';
    await s.openFilters();
    await s.testid('invoices-filters-clear').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.query).toEqual({});
    expect(s.params().at(-1)).toEqual({ search: '0004', limit: 25, offset: 0 });
  });

  it('opens on the business of the address (`?business=`), with its status', async () => {
    const s = await setup('/billing/invoices?business=plaza&status=open');
    expect(s.params()).toEqual([{ hub_id: 'plaza', status: 'open', limit: 25, offset: 0 }]);
    await s.show([OPEN]);
    await s.openFilters();
    expect((s.testid('invoices-business').element as HTMLElement & { value: unknown }).value).toBe('plaza');
    expect((s.testid('invoices-status').element as HTMLElement & { value: unknown }).value).toBe('open');
    expect(s.testid('invoices-unknown-business').exists()).toBe(false);
  });

  it('a business of the address that is not the account’s: every invoice, saying so', async () => {
    const s = await setup('/billing/invoices?business=xyz');
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
    const download = vi.spyOn(browser, 'download').mockImplementation(() => {});
    const s = await setup('/billing/invoices?business=bakery&year=2026');
    await s.show([PAID]);
    const csv = s.testid('invoices-csv');
    // On a phone it reads «Excel» (the toolbar stays on two lines); its name is the whole one everywhere.
    expect(csv.get('.csv-label--long').text()).toBe('Download Excel');
    expect(csv.get('.csv-label--short').text()).toBe('Excel');
    expect(accessibleName(csv)).toBe('Download Excel');
    expect(csv.attributes('title')).toBe('The list of what the filters show, for your accountant (it opens in Excel)');
    await csv.trigger('click');
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/csv?hub_id=bakery&year=2026');
  });
});

describe('InvoicesTab: selection', () => {
  it('«Download PDF (n)» downloads the selected ones issued, and says which are still being issued', async () => {
    const download = vi.spyOn(browser, 'download').mockImplementation(() => {});
    const s = await setup();
    await s.show();
    expect(s.testid('invoices-pdf-selected').exists()).toBe(false);
    s.table().vm.$emit('update:selected', ['00123', '00124']);
    await flush();
    const button = s.testid('invoices-pdf-selected');
    expect(button.text()).toBe('Download PDF (2)');
    await button.trigger('click');
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/pdf?id=00123');
    expect(toastInfo).toHaveBeenCalledWith('That invoice is still being issued: its PDF is ready in a few minutes.');
  });

  it('keeps the rows selected on another page', async () => {
    const download = vi.spyOn(browser, 'download').mockImplementation(() => {});
    const s = await setup();
    await s.show([PAID], [BAKERY], 1, { total: 30 });
    s.table().vm.$emit('update:selected', ['00123']);
    await flush();
    await s.show([invoiceRow('00200')], [BAKERY], 2, { total: 30, offset: 25 });
    s.table().vm.$emit('update:selected', ['00123', '00200']);
    await flush();
    await s.testid('invoices-pdf-selected').trigger('click');
    expect(download.mock.calls.map(([url]) => url)).toEqual(['/api/billing/invoices/pdf?id=00123', '/api/billing/invoices/pdf?id=00200']);
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
    expect(s.testid('invoices-empty-plans').attributes('routerlink')).toBe('/store/plans');
  });

  it('inside the apps, the same without selling', async () => {
    applySurface('desktop');
    const s = await setup();
    await s.show([]);
    expect(s.testid('invoices-empty').text()).toContain('No invoices yet');
    expect(s.testid('invoices-empty-plans').exists()).toBe(false);
  });

  it('a business on Free says it has none', async () => {
    const s = await setup('/billing/invoices?business=cafe');
    await s.show([]);
    expect(s.testid('invoices-empty').text()).toContain('Café Central is on Free: it has no invoices.');
  });

  it('filters that find nothing keep the toolbar and offer to show everything', async () => {
    const s = await setup('/billing/invoices?status=open&year=2024');
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
    const s = await setup('/billing/invoices', undefined, 'es');
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

