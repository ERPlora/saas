// The invoices' PDFs on their own: what is asked for, what is said, and what the selection counts. The tab's tests
// (`components/InvoicesTab.downloads.test.ts`) press its buttons; these call the pieces directly.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('../../hubs/frontend/__tests__/module-mocks')).shellWithToastSpies(original));

import { toastError, toastInfo } from '@erplora/ui/shell';
import { ApiError } from '@erplora/ui/sdk';
import { defineComponent, shallowRef } from 'vue';

import type { InvoiceRowOut } from '../../frontend/sdk-types/billing-invoices';
import { invoiceRow, unpaidRow } from './__tests__/billing-fixtures';
import { flush, mountBilling } from './__tests__/mount-billing';
import { browser } from './browser';
import { useInvoicePdfs, useSelectedPdfs } from './invoice-pdfs';

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastInfo).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

const PAID = invoiceRow('00123');
const ISSUING = invoiceRow('00124', { fiscal_status: 'issuing', actions: [], can: { pay: false, pdf: false } });
const OPEN = unpaidRow('i9');

/** The pieces as the tab holds them; the rows arrive afterwards, as the live list sends them. */
async function setup(rows: InvoiceRowOut[]) {
  const list = shallowRef<InvoiceRowOut[]>([]);
  const chosen = shallowRef<string[]>([]);
  let pdfs!: ReturnType<typeof useInvoicePdfs>;
  let selection!: ReturnType<typeof useSelectedPdfs>;
  const Host = defineComponent({
    setup() {
      pdfs = useInvoicePdfs(list);
      selection = useSelectedPdfs(list, chosen, pdfs.notIssued);
      return () => null;
    },
  });
  await mountBilling(Host);
  list.value = rows;
  await flush();
  return { list, chosen, pdfs, selection };
}

describe('useInvoicePdfs', () => {
  it('never asks for a PDF the row says is not there yet, nor again for one the server said is still being issued', async () => {
    const download = vi
      .spyOn(browser, 'download')
      .mockRejectedValue(new ApiError(404, 'billing.invoice_not_issued', 'This invoice is still being issued.'));
    const { pdfs } = await setup([ISSUING, PAID]);
    await pdfs.downloadPdfs([ISSUING]);
    expect(download).not.toHaveBeenCalled();
    expect(toastInfo).toHaveBeenLastCalledWith('This invoice is still being issued: its PDF will be ready as soon as it finishes.');
    await pdfs.downloadPdfs([PAID]);
    expect(pdfs.notIssued.value.has('00123')).toBe(true);
    await pdfs.downloadPdfs([PAID]);
    expect(download).toHaveBeenCalledOnce();
    expect(toastInfo).toHaveBeenCalledTimes(3);
    expect(toastError).not.toHaveBeenCalled();
  });
});

describe('useSelectedPdfs', () => {
  it('counts the selected rows as last seen, also once they left the list: issued, unpaid and still being issued', async () => {
    const { list, chosen, selection } = await setup([OPEN, ISSUING, PAID]);
    chosen.value = ['i9', '00124', '00123'];
    list.value = [invoiceRow('00200')];
    await flush();
    expect(selection.selection.value.issued.map((row) => row.id)).toEqual(['00123']);
    expect(selection.selection.value).toMatchObject({ unpaid: 1, issuing: 1 });
    expect(selection.selectionNote.value).toBe(
      '1 selected invoice is unpaid: an unpaid invoice has no PDF until it is paid. 1 selected invoice is still being issued: its PDF is ready in a few minutes.',
    );
  });
});
