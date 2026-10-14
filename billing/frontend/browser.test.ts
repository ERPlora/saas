// What the Billing section asks of the browser itself: going to Stripe (its page to pay an invoice, its
// Customer Portal) and downloading a file the API answers as an attachment (an invoice's PDF, the CSV of
// the list). A download asks for the file (`Accept`, the session cookie) and saves it only when the answer
// IS that file: an error (a 503 of the invoice service, a 404 of one still being issued, a proxy's page) is
// never saved as `pdf.json` (audit 2026-10-14, R-05); it is thrown as the API's error, for the page to say.
import { ApiError } from '@erplora/ui/sdk';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { attachmentName, browser, operationUrl, REVOKE_AFTER_MS } from './browser';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
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

describe('attachmentName', () => {
  it('is the file name the server gives (`Content-Disposition`), plain or encoded (RFC 6266)', () => {
    expect(attachmentName('attachment; filename="ERP-2026-00123.pdf"')).toBe('ERP-2026-00123.pdf');
    expect(attachmentName('attachment; filename=erplora-invoices-2026-10-14.csv')).toBe('erplora-invoices-2026-10-14.csv');
    expect(attachmentName(`attachment; filename="facturas.csv"; filename*=UTF-8''facturas%20de%20octubre.csv`)).toBe('facturas de octubre.csv');
    expect(attachmentName(null)).toBe('');
    expect(attachmentName('attachment')).toBe('');
  });
});

describe('browser.download', () => {
  /** The fake network: one answer for every request; what was asked, kept. */
  function serve(answer: () => Response | Promise<Response>) {
    const asked: Array<{ url: string; init: RequestInit }> = [];
    vi.stubGlobal('fetch', (url: string, init: RequestInit) => {
      asked.push({ url, init });
      return Promise.resolve(answer());
    });
    return asked;
  }
  /** What the page hands the browser to save: the anchors clicked and the object URLs made and revoked. */
  function watchSaves() {
    const clicked: Array<{ href: string; download: string; inDocument: boolean }> = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ href: this.getAttribute('href') ?? '', download: this.getAttribute('download') ?? 'none', inDocument: this.isConnected });
    });
    const blobs: Blob[] = [];
    const create = vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      blobs.push(blob as Blob);
      return `blob:http://localhost/${blobs.length}`;
    });
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    return { clicked, blobs, create, revoke };
  }
  const pdf = () =>
    new Response(new Blob(['%PDF-1.7'], { type: 'application/pdf' }), {
      status: 200,
      headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="ERP-2026-00123.pdf"' },
    });
  const envelope = (status: number, code: string, message: string) => Response.json({ error: { code, message } }, { status });

  it('asks for the PDF with the session cookie and saves it under the server’s name, then lets the URL go', async () => {
    vi.useFakeTimers();
    const asked = serve(pdf);
    const saves = watchSaves();
    await browser.download('/api/billing/invoices/pdf?id=i-1', 'application/pdf');
    expect(asked).toEqual([
      { url: '/api/billing/invoices/pdf?id=i-1', init: { headers: { Accept: 'application/pdf' }, credentials: 'same-origin' } },
    ]);
    expect(await saves.blobs[0].text()).toBe('%PDF-1.7');
    expect(saves.clicked).toEqual([{ href: 'blob:http://localhost/1', download: 'ERP-2026-00123.pdf', inDocument: true }]);
    expect(document.querySelectorAll('a')).toHaveLength(0);
    expect(saves.revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(REVOKE_AFTER_MS);
    expect(saves.revoke).toHaveBeenCalledExactlyOnceWith('blob:http://localhost/1');
  });

  it('a CSV is asked as CSV, and its charset does not make it another file', async () => {
    const asked = serve(
      () =>
        new Response('\ufeffInvoice,Date\n', {
          status: 200,
          headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="erplora-invoices-2026-10-14.csv"' },
        }),
    );
    const saves = watchSaves();
    await browser.download('/api/billing/invoices/csv', 'text/csv');
    expect(asked[0].init).toEqual({ headers: { Accept: 'text/csv' }, credentials: 'same-origin' });
    expect(saves.clicked.map((c) => c.download)).toEqual(['erplora-invoices-2026-10-14.csv']);
  });

  it('without a name from the server, a name of its kind', async () => {
    serve(() => new Response('%PDF', { status: 200, headers: { 'Content-Type': 'application/pdf' } }));
    const saves = watchSaves();
    await browser.download('/api/billing/invoices/pdf?id=i-1', 'application/pdf');
    expect(saves.clicked.map((c) => c.download)).toEqual(['invoice.pdf']);
  });

  it.each([
    [503, 'billing.platform_unavailable', 'The invoice cannot be downloaded right now. Try again in a moment.'],
    [404, 'billing.invoice_not_issued', 'This invoice is still being issued: its PDF is ready once it is.'],
  ])('an error of the API (%i) is thrown as such and nothing is saved', async (status, code, message) => {
    serve(() => envelope(status, code, message));
    const saves = watchSaves();
    const failure = await browser.download('/api/billing/invoices/pdf?id=i-1', 'application/pdf').catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status, code, message });
    expect(saves.create).not.toHaveBeenCalled();
    expect(saves.clicked).toEqual([]);
  });

  it('an answer that is not the file asked for (a proxy’s page, JSON) is never saved', async () => {
    serve(() => new Response('<html>Bad gateway</html>', { status: 200, headers: { 'Content-Type': 'text/html' } }));
    const saves = watchSaves();
    const failure = await browser.download('/api/billing/invoices/pdf?id=i-1', 'application/pdf').catch((error: unknown) => error);
    expect(failure).toMatchObject({ code: 'unexpected_response', status: 200 });
    expect(saves.clicked).toEqual([]);
  });

  it('without network, the SDK’s network error', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    const saves = watchSaves();
    const failure = await browser.download('/api/billing/invoices/csv', 'text/csv').catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: 'network_error', status: 0 });
    expect(saves.clicked).toEqual([]);
  });
});
