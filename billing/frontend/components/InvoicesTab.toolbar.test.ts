// Billing → Invoices, its toolbar: the filters by business, status and year, the search by number and
// «Download Excel», kept on one line from 641 px.
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { mockResizeObserver } from '../../../packages/ui/src/components/DataTable/__tests__/harness';
import { OPEN, PAID, setup, setUpInvoicesTab } from '../__tests__/invoices-tab';
import { accessibleName, flush, optionValue } from '../__tests__/mount-billing';
import { browser } from '../browser';

setUpInvoicesTab();

describe('InvoicesTab: filters and search', () => {
  it('filters by business (the ones the account owns or pays), status and year, from one «Filters» control', async () => {
    const s = await setup();
    await s.show();
    // One control in the toolbar: the filters live in its popover.
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

describe('InvoicesTab: the toolbar on one line from 641 px', () => {
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
