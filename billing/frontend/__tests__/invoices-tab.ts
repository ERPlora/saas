// The invoices tab (`InvoicesTab`) mounted for its tests: the account's businesses and its invoices arrive through
// the live lists, on a desk wider than the table's card breakpoint. A test file mocks `@erplora/ui/shell` as the
// panel's tests do and calls `setUpInvoicesTab()` at its top.
import { DataTable } from '@erplora/ui/components';
import { applySurface, toastError, toastInfo } from '@erplora/ui/shell';
import { afterEach, beforeEach, vi } from 'vitest';
import type { Component } from 'vue';

import { resultFrame } from '../../../hubs/frontend/__tests__/mount-hubs';
import InvoicesTab from '../components/InvoicesTab.vue';
import { invoicePage, invoiceRow, unpaidRow } from './billing-fixtures';
import { BAKERY, businessPage, businessRow, CAFE, PLAZA } from './fixtures';
import { describeCall, flush, mountBilling, type StreamCall } from './mount-billing';

/** A desk wider than the table's card breakpoint (1100 px): the list, not the cards. */
const DESK = { width: 1440, height: 900 };
const viewport = (size: { width: number; height: number }) =>
  (window as unknown as { happyDOM: { setViewport(v: { width: number; height: number }): void } }).happyDOM.setViewport(size);

export function setUpInvoicesTab(): void {
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
}

export const PAID = invoiceRow('00123', { business: { id: 'bakery', name: 'Panadería López' }, date: '2026-10-01' });
export const ISSUING = invoiceRow('00124', {
  business: { id: 'bakery', name: 'Panadería López' },
  fiscal_status: 'issuing',
  fiscal_status_label: 'Issuing',
  actions: [],
  can: { pay: false, pdf: false },
});
export const OPEN = unpaidRow('i9', { reference: 'A1B2-0004' });
export const ROWS = [OPEN, ISSUING, PAID];
/** A business the account works in but neither owns nor pays: its invoices are not the account's. */
const SALON = businessRow('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager', is_payer: false });

export async function setup(path = '/dashboard/billing/invoices', api: (call: ReturnType<typeof describeCall>) => Response = () => Response.json({}), locale: 'en' | 'es' = 'en') {
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
