// What the Billing section asks of the browser itself: going to Stripe (its page to pay an invoice, its
// Customer Portal) and downloading a file the API answers as an attachment (an invoice's PDF, the CSV of
// the list). A download is the browser's own GET with the session cookie, not a `fetch` of ours: the SPA
// reaches the server only through the SDK (eslint `no-restricted-globals`), whose `api.call` reads JSON.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browser, operationUrl } from './browser';

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('operationUrl', () => {
  it('is the route of a query with its input as the query string', () => {
    expect(operationUrl('billing.invoice.pdf', { id: 'i-1' })).toBe('/api/billing/invoices/pdf?id=i-1');
  });

  it('leaves out what is not set, so the CSV holds every invoice the filters show', () => {
    expect(operationUrl('billing.invoice.csv', { hub_id: 'h 1', status: null, year: 2026, search: '' })).toBe(
      '/api/billing/invoices/csv?hub_id=h+1&year=2026',
    );
    expect(operationUrl('billing.invoice.csv', {})).toBe('/api/billing/invoices/csv');
  });

  it('refuses a command: a download is a GET', () => {
    expect(() => operationUrl('billing.invoice.pay' as never, { id: 'i-1' })).toThrow(/not a query/);
  });
});

describe('browser.download', () => {
  it('lets the browser download the file: a same-origin link with `download`, clicked once and removed', () => {
    const clicked: Array<{ href: string; download: string; inDocument: boolean }> = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ href: this.getAttribute('href') ?? '', download: this.getAttribute('download') ?? 'none', inDocument: this.isConnected });
    });
    browser.download('/api/billing/invoices/pdf?id=i-1');
    expect(clicked).toEqual([{ href: '/api/billing/invoices/pdf?id=i-1', download: '', inDocument: true }]);
    expect(document.querySelectorAll('a')).toHaveLength(0);
  });
});
