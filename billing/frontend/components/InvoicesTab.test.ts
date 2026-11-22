// Billing → Invoices: ERPlora's invoices of all the account's businesses in a server-side DataTable, cards up to
// 1100 px, with filters, a search by number, «Pay» for one not collected, its PDF once issued and «Download Excel».
// The toolbar (filters, search and «Download Excel») is tested in InvoicesTab.toolbar.test.ts, and the files the
// tab downloads in InvoicesTab.downloads.test.ts.
import { applySurface } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { errorFrame, HELLO, resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
import { invoicePage, invoiceRow, unpaidRow } from '../__tests__/billing-fixtures';
import { BAKERY, businessPage } from '../__tests__/fixtures';
import { OPEN, PAID, ROWS, setup, setUpInvoicesTab } from '../__tests__/invoices-tab';
import { accessibleName, describeCall, flush, mountBilling } from '../__tests__/mount-billing';
import { browser } from '../browser';
import InvoicesTab from './InvoicesTab.vue';

setUpInvoicesTab();

describe('InvoicesTab: the list', () => {
  // One page of `billing.invoice.list` holds 100 rows at most; on a phone
  // the end of the scroll never asks for more, and past them the table pages instead (`maxWindow`).
  it('on a phone the end of the scroll grows one window from the first row, never past the server’s 100 rows', async () => {
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
      // A card's title is its number: the body does not repeat it («Invoice ERP-2026-00123»).
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

  it('per row, «Pay» (fixed and labelled) for one not collected, the PDF once issued and «View invoice», each named with its invoice', async () => {
    const s = await setup();
    await s.show();
    const actions = s.prop<Array<Record<string, unknown>>>('actions');
    expect(actions.map((a) => [a.id, !!a.pinned, !!a.showLabel])).toEqual([
      ['pay', true, true],
      ['pdf', false, false],
      ['view', false, false],
    ]);
    const ids = (row: string) => s.wrapper.findAll(`[data-testid^="invoices-row-${row}-"]`).map((b) => b.attributes('data-testid')!.split('-').pop());
    expect(['i9', '00124', '00123'].map(ids)).toEqual([['pay', 'view'], ['view'], ['pdf', 'view']]);
    const named = (id: string) => [s.testid(`invoices-row-${id}`).text(), accessibleName(s.testid(`invoices-row-${id}`))];
    expect(['i9-pay', '00123-pdf'].map(named)).toEqual([['Pay', 'Pay: A1B2-0004'], ['', 'Download PDF: ERP-2026-00123']]);
  });

  it('«View invoice» opens the page of that invoice', async () => {
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

describe('InvoicesTab: a list that does not load says so, never «No invoices yet»', () => {
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

describe('InvoicesTab: a clean page', () => {
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
