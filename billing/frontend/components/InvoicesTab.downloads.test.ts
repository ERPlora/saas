// Billing → Invoices, the files: «Download PDF (n)» over the selected invoices, and a PDF or the Excel saved only
// when the server answers with the file.
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('../../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { toastError, toastInfo } from '@erplora/ui/shell';

import { invoiceRow, unpaidRow } from '../__tests__/billing-fixtures';
import { BAKERY } from '../__tests__/fixtures';
import { ISSUING, OPEN, PAID, setup, setUpInvoicesTab } from '../__tests__/invoices-tab';
import { accessibleName, flush } from '../__tests__/mount-billing';
import { browser } from '../browser';

setUpInvoicesTab();

describe('InvoicesTab: selection', () => {
  // «Download PDF (n)» counts only the issued ones; what has no PDF yet is said above the list,
  // unpaid apart («still being issued» was false for an invoice that is not paid).
  it('«Download PDF (n)» counts and downloads the selected ones issued; the others are said above the list', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup();
    await s.show();
    expect(s.testid('invoices-pdf-selected').exists()).toBe(false);
    s.table().vm.$emit('update:selected', ['00123', '00124']);
    await flush();
    const button = s.testid('invoices-pdf-selected');
    // Its icon and the count; the whole label names it and is its title.
    expect([button.text(), accessibleName(button), button.attributes('title')]).toEqual(['1', 'Download PDF (1)', 'Download PDF (1)']);
    expect(s.testid('invoices-selection-note').text()).toBe('1 selected invoice is still being issued: its PDF is ready in a few minutes.');
    await button.trigger('click');
    await flush();
    expect(download).toHaveBeenCalledExactlyOnceWith('/api/billing/invoices/pdf?id=00123', 'application/pdf');
    expect(toastInfo).not.toHaveBeenCalled();
  });

  it('unpaid invoices have no PDF: they are not counted, and the note says why', async () => {
    const download = vi.spyOn(browser, 'download').mockResolvedValue();
    const s = await setup();
    await s.show([OPEN, unpaidRow('i10'), PAID]);
    s.table().vm.$emit('update:selected', ['i9', 'i10', '00123']);
    await flush();
    expect(accessibleName(s.testid('invoices-pdf-selected'))).toBe('Download PDF (1)');
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
    expect([button.text(), accessibleName(button)]).toEqual(['0', 'Download PDF (0)']);
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
    expect(accessibleName(s.testid('invoices-pdf-selected'))).toBe('Descargar PDF (1)');
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

  it('with nothing selected there is no note; unpaid and still being issued ones selected are said one after the other', async () => {
    const s = await setup();
    await s.show([OPEN, ISSUING, PAID]);
    expect(s.testid('invoices-selection-note').exists()).toBe(false);
    s.table().vm.$emit('update:selected', ['i9', '00124']);
    await flush();
    expect(s.testid('invoices-selection-note').text()).toBe(
      '1 selected invoice is unpaid: an unpaid invoice has no PDF until it is paid. 1 selected invoice is still being issued: its PDF is ready in a few minutes.',
    );
  });

  it('follows the list: a selected invoice paid and issued meanwhile counts for «Download PDF (n)» and leaves the note', async () => {
    const s = await setup();
    await s.show([OPEN, PAID]);
    s.table().vm.$emit('update:selected', ['i9']);
    await flush();
    expect(accessibleName(s.testid('invoices-pdf-selected'))).toBe('Download PDF (0)');
    await s.show([invoiceRow('i9'), PAID], undefined, 2);
    expect(accessibleName(s.testid('invoices-pdf-selected'))).toBe('Download PDF (1)');
    expect(s.testid('invoices-selection-note').exists()).toBe(false);
  });
});

describe('InvoicesTab: a file is saved only when it is the file', () => {
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
  const notIssued = () => envelope(404, 'billing.invoice_not_issued', 'This invoice is still being issued: its PDF is ready once it is.');
  /** 00123 and 00125 on the list and both selected; the file of 00123 is answered by `first`, the other by `second`. */
  async function selectBoth(first: () => Response, second: () => Response, locale: 'en' | 'es' = 'en') {
    serveFiles((url) => (url.endsWith('00123') ? first() : second()));
    const saved = watchSaves();
    const s = await setup('/dashboard/billing/invoices', undefined, locale);
    await s.show([PAID, invoiceRow('00125')]);
    s.table().vm.$emit('update:selected', ['00123', '00125']);
    await flush();
    return { s, saved };
  }

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
    const down = () => envelope(503, 'billing.platform_unavailable', 'The invoice cannot be downloaded right now. Try again in a moment.');
    const { s, saved } = await selectBoth(down, down);
    await press(s, 'invoices-pdf-selected');
    expect(saved).toEqual([]);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('The invoice service is not answering. Try again in a moment.');
  });

  // One press, one notice: a failure and invoices still being issued in the same download are said together, in the
  // error, never as two notices for one download.
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
    const { s } = await selectBoth(
      () => envelope(503, 'billing.platform_unavailable', 'Ahora no se puede descargar la factura.'),
      () => envelope(404, 'billing.invoice_not_issued', 'Esta factura aún se está emitiendo.'),
      'es',
    );
    await press(s, 'invoices-pdf-selected');
    expect(toastError).toHaveBeenCalledExactlyOnceWith(
      'El servicio de facturas no responde. Prueba de nuevo en un momento. Esa factura aún se está emitiendo: su PDF estará en unos minutos.',
    );
    expect(toastInfo).not.toHaveBeenCalled();
  });

  // A notice is one line of text (Material's snackbar): its sentences one after the other, each with its stop, never a
  // line break (painted as a bare space) nor two sentences run together when the server's words end without one.
  it('what failed and what is still being issued read as two sentences on one line, even without the server’s stop', async () => {
    const { s } = await selectBoth(() => envelope(503, 'service_unavailable', 'The service is not available right now'), notIssued);
    await press(s, 'invoices-pdf-selected');
    const said = String(vi.mocked(toastError).mock.calls[0]?.[0]);
    expect(said).not.toMatch(/\n/);
    expect(said).toBe('The service is not available right now. That invoice is still being issued: its PDF is ready in a few minutes.');
  });

  it('a PDF being asked for shows its progress and cannot be asked again until the answer comes', async () => {
    let answer!: (response: Response) => void;
    vi.stubGlobal('fetch', () => new Promise<Response>((resolve) => (answer = resolve)));
    watchSaves();
    const s = await setup();
    await s.show();
    await press(s, 'invoices-row-00123-pdf');
    expect(pdfAction(s).disabled).toBe(true);
    expect(s.testid('invoices-row-00123-pdf').find('ion-spinner').exists()).toBe(true);
    answer(new Response('%PDF', { status: 200, headers: { 'Content-Type': 'application/pdf' } }));
    await flush();
    expect(pdfAction(s).disabled).toBe(false);
    expect(s.testid('invoices-row-00123-pdf').find('ion-spinner').exists()).toBe(false);
  });

  it('«Download PDF (n)» with two different failures says the first one', async () => {
    const { s } = await selectBoth(
      () => envelope(503, 'billing.platform_unavailable', 'The invoice cannot be downloaded right now. Try again in a moment.'),
      () => envelope(500, 'internal_error', 'Something went wrong.'),
    );
    await press(s, 'invoices-pdf-selected');
    expect(toastError).toHaveBeenCalledExactlyOnceWith('The invoice service is not answering. Try again in a moment.');
  });

  it('the server’s words read as one sentence on one line: its line breaks and spaces go, its own stop stays', async () => {
    const { s } = await selectBoth(() => envelope(503, 'service_unavailable', 'The service is busy\n  right now!  '), notIssued);
    await press(s, 'invoices-pdf-selected');
    expect(toastError).toHaveBeenCalledExactlyOnceWith(
      'The service is busy right now! That invoice is still being issued: its PDF is ready in a few minutes.',
    );
  });

  it('one the server says is still being issued stops counting for «Download PDF (n)» and joins the note', async () => {
    const { s } = await selectBoth(() => new Response('%PDF', { status: 200, headers: { 'Content-Type': 'application/pdf' } }), notIssued);
    expect(accessibleName(s.testid('invoices-pdf-selected'))).toBe('Download PDF (2)');
    await press(s, 'invoices-pdf-selected');
    expect(accessibleName(s.testid('invoices-pdf-selected'))).toBe('Download PDF (1)');
    expect(s.testid('invoices-selection-note').text()).toBe('1 selected invoice is still being issued: its PDF is ready in a few minutes.');
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
