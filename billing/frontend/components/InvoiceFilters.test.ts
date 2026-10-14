// The filters of Billing → Invoices in one control of the toolbar (Ioan, 2026-10-14: a clean SaaS, one line of
// toolbar at 1440 px): a «Filters» button that says how many are on, and a popover with the business (a select),
// the status (a segment: three visible options) and the year (a select), plus «Clear filters» while any is on.
// It keeps no state: the page holds the filters (in the address) and hears `change` and `clear`.
import { afterEach, describe, expect, it } from 'vitest';

import { accessibleName, flush, ionProps, mountBilling, optionValue } from '../__tests__/mount-billing';
import InvoiceFilters from './InvoiceFilters.vue';

const BUSINESSES = [
  { id: 'plaza', name: 'Bar La Plaza' },
  { id: 'bakery', name: 'Panadería López' },
];
const YEARS = [2026, 2025, 2024];

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const s = await mountBilling(InvoiceFilters, {
    locale,
    props: { businesses: BUSINESSES, years: YEARS, business: null, status: null, year: null, ...props },
  });
  const testid = (id: string) => s.wrapper.find(`[data-testid="${id}"]`);
  const open = async () => {
    await testid('invoices-filters').trigger('click');
    await flush();
  };
  const change = async (id: string, value: unknown) => {
    testid(id).element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  };
  const emitted = () => s.wrapper.emitted('change') ?? [];
  /** An `aria-*` of an ion-button: Ionic moves it from the host onto its inner button. */
  const aria = (id: string, name: string) => {
    const host = testid(id).element;
    return host.getAttribute(name) ?? host.shadowRoot?.querySelector('button')?.getAttribute(name) ?? null;
  };
  return { ...s, testid, open, change, emitted, aria };
}

describe('InvoiceFilters: one «Filters» control', () => {
  it('is a button of the toolbar; its controls only show in its popover', async () => {
    const s = await setup();
    expect(s.testid('invoices-filters').text()).toBe('Filters');
    expect(s.testid('invoices-filters-count').exists()).toBe(false);
    expect(s.aria('invoices-filters', 'aria-haspopup')).toBe('dialog');
    expect(s.aria('invoices-filters', 'aria-expanded')).toBe('false');
    expect(s.testid('invoices-business').exists()).toBe(false);
    await s.open();
    expect(s.aria('invoices-filters', 'aria-expanded')).toBe('true');
    expect(s.testid('invoices-filters-panel').exists()).toBe(true);
  });

  it('offers the business and the year as popover selects, never an action sheet', async () => {
    const s = await setup();
    await s.open();
    const business = s.testid('invoices-business');
    expect(ionProps(business, 'interface', 'mode', 'fill', 'label')).toEqual({ interface: 'popover', mode: 'md', fill: 'outline', label: 'Business' });
    expect(business.findAll('ion-select-option').map((o) => [optionValue(o), o.text()])).toEqual([
      ['', 'All businesses'],
      ['plaza', 'Bar La Plaza'],
      ['bakery', 'Panadería López'],
    ]);
    const year = s.testid('invoices-year');
    expect(ionProps(year, 'interface', 'label')).toEqual({ interface: 'popover', label: 'Year' });
    expect(year.findAll('ion-select-option').map((o) => o.text())).toEqual(['All years', '2026', '2025', '2024']);
  });

  it('offers the status as a segment of its three options', async () => {
    const s = await setup();
    await s.open();
    const status = s.testid('invoices-status');
    expect(status.element.tagName.toLowerCase()).toBe('ion-segment');
    expect(status.findAll('ion-segment-button').map((b) => [(b.element as HTMLElement & { value?: string }).value, b.text()])).toEqual([
      ['all', 'All'],
      ['paid', 'Paid'],
      ['open', 'Not collected'],
    ]);
    expect((status.element as HTMLElement & { value?: string }).value).toBe('all');
    expect(s.testid('invoices-status-label').text()).toBe('Status');
  });

  it('says each choice to the page, `` for «All»', async () => {
    const s = await setup();
    await s.open();
    await s.change('invoices-business', 'bakery');
    await s.change('invoices-status', 'open');
    await s.change('invoices-status', 'all');
    await s.change('invoices-year', 2025);
    await s.change('invoices-year', '');
    expect(s.emitted()).toEqual([
      ['business', 'bakery'],
      ['status', 'open'],
      ['status', ''],
      ['year', 2025],
      ['year', ''],
    ]);
  });

  it('shows the filters that are on: on the button, in the controls, and «Clear filters»', async () => {
    const s = await setup({ business: 'bakery', status: 'paid', year: 2025 });
    expect(s.testid('invoices-filters-count').text()).toBe('3');
    expect(accessibleName(s.testid('invoices-filters'))).toBe('Filters: 3 on');
    await s.open();
    expect((s.testid('invoices-business').element as HTMLElement & { value?: unknown }).value).toBe('bakery');
    expect((s.testid('invoices-status').element as HTMLElement & { value?: unknown }).value).toBe('paid');
    expect((s.testid('invoices-year').element as HTMLElement & { value?: unknown }).value).toBe(2025);
    await s.testid('invoices-filters-clear').trigger('click');
    await flush();
    expect(s.wrapper.emitted('clear')).toHaveLength(1);
  });

  it('without filters on there is nothing to clear', async () => {
    const s = await setup();
    await s.open();
    expect(s.testid('invoices-filters-clear').exists()).toBe(false);
    expect(accessibleName(s.testid('invoices-filters'))).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ status: 'open' }, 'es');
    expect(s.testid('invoices-filters').text()).toContain('Filtros');
    expect(accessibleName(s.testid('invoices-filters'))).toBe('Filtros: 1 activo');
    await s.open();
    expect(s.testid('invoices-status').findAll('ion-segment-button').map((b) => b.text())).toEqual(['Todas', 'Pagadas', 'No cobradas']);
    expect(ionProps(s.testid('invoices-business'), 'label')).toEqual({ label: 'Negocio' });
    expect(s.testid('invoices-filters-clear').text()).toBe('Quitar filtros');
  });
});
