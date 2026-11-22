// The invoices' PDFs in Billing → Invoices: one row's or the selected ones', saved only when the answer is the file
// (`browser.ts`). One still being issued (404) says so and waits, as «Issuing» does, until the list sends its row
// changed; the invoice service down (503) says it. The selection counts the issued ones and names the others.
import { toastError, toastInfo } from '@erplora/ui/shell';
import type { ApiError } from '@erplora/ui/sdk';
import { computed, type Ref, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { InvoiceRowOut } from '../../frontend/sdk-types/billing-invoices';
import { useErrorText } from '../../hubs/frontend/error-text';
import { browser, operationUrl } from './browser';

type Rows = Readonly<Ref<InvoiceRowOut[]>>;
/** The invoices the server said are still being issued, with their row as it was then. */
type NotIssued = Readonly<Ref<ReadonlyMap<string, string>>>;

function withId(set: ReadonlySet<string>, id: string, on: boolean): Set<string> {
  const next = new Set(set);
  if (on) next.add(id);
  else next.delete(id);
  return next;
}

/** One notice from several sentences: one after the other on one line, each ending with its stop. A notice is one
 *  line of text (Material's snackbar): a line break would paint as a bare space between two sentences. */
function sentences(parts: readonly string[]): string {
  return parts
    .map((part) => part.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .map((part) => (/[.!?…]$/.test(part) ? part : `${part}.`))
    .join(' ');
}

/** The invoices the server said are still being issued (404 `billing.invoice_not_issued`), with their row as it
 *  was then: their PDF waits, as «Issuing» does, until the list sends that row changed. */
function useNotIssued(rows: Rows) {
  const notIssued = shallowRef(new Map<string, string>());
  watch(rows, (now) => {
    if (!notIssued.value.size) return;
    const next = new Map(notIssued.value);
    for (const row of now) if (next.get(row.id) !== undefined && next.get(row.id) !== JSON.stringify(row)) next.delete(row.id);
    if (next.size !== notIssued.value.size) notIssued.value = next;
  });
  return notIssued;
}

export function useInvoicePdfs(rows: Rows) {
  const { t } = useI18n();
  const { text } = useErrorText();
  const notIssued = useNotIssued(rows);
  /** The PDFs being asked for now. */
  const fetching = shallowRef(new Set<string>());

  /** What a failed file says; `null` for one still being issued (said apart). */
  function fileError(error: ApiError): string | null {
    if (error.code === 'billing.invoice_not_issued') return null;
    if (error.code === 'billing.platform_unavailable') return t('billing.invoices.pdfUnavailable');
    return text(error);
  }

  /** Downloads the PDF of each issued one, one after the other; says in one notice what failed (once, not per file)
   *  and how many are still being issued. Alone, one still being issued says so in its own words. */
  async function downloadPdfs(invoices: InvoiceRowOut[]): Promise<void> {
    let waiting = 0;
    let failure: string | null = null;
    for (const invoice of invoices) {
      if (!invoice.can.pdf || notIssued.value.has(invoice.id)) {
        waiting += 1;
        continue;
      }
      fetching.value = withId(fetching.value, invoice.id, true);
      try {
        await browser.download(operationUrl('billing.invoice.pdf', { id: invoice.id }), 'application/pdf');
      } catch (error) {
        const said = fileError(error as ApiError);
        if (said === null) {
          notIssued.value = new Map(notIssued.value).set(invoice.id, JSON.stringify(invoice));
          waiting += 1;
        } else {
          console.error('billing: an invoice PDF could not be downloaded', error);
          failure ??= said;
        }
      } finally {
        fetching.value = withId(fetching.value, invoice.id, false);
      }
    }
    const alone = invoices.length === 1;
    const issuing = !waiting
      ? ''
      : alone
        ? t('billing.invoices.pdfIssuing')
        : t('billing.invoices.pdfNotReady', { count: waiting }, waiting);
    // One press, one notice: what failed, then what is still being issued, never two notices for one download.
    if (failure) toastError(sentences([failure, issuing]));
    else if (issuing) toastInfo(issuing);
  }

  return { notIssued, fetching, downloadPdfs };
}

/** The selected invoices that have their PDF, and how many have none yet: unpaid (an unpaid invoice has no PDF
 *  until it is paid) or paid and still being issued. The selection is kept across pages: each selected row as it
 *  was last seen. */
export function useSelectedPdfs(rows: Rows, selected: Readonly<Ref<string[]>>, notIssued: NotIssued) {
  const { t } = useI18n();
  const seen = new Map<string, InvoiceRowOut>();
  watch(rows, (now) => {
    for (const row of now) seen.set(row.id, row);
  });

  const selection = computed(() => {
    void rows.value; // `seen` follows the list
    const hasPdf = (row: InvoiceRowOut) => row.can.pdf && !notIssued.value.has(row.id);
    const chosen = selected.value.flatMap((id) => seen.get(id) ?? []);
    return {
      issued: chosen.filter(hasPdf),
      unpaid: chosen.filter((row) => row.payment_status === 'open').length,
      issuing: chosen.filter((row) => row.payment_status === 'paid' && !hasPdf(row)).length,
    };
  });
  const selectionNote = computed(() => {
    const { unpaid, issuing } = selection.value;
    return [
      unpaid ? t('billing.invoices.selectedUnpaid', { count: unpaid }, unpaid) : '',
      issuing ? t('billing.invoices.selectedIssuing', { count: issuing }, issuing) : '',
    ]
      .filter(Boolean)
      .join(' ');
  });

  return { selection, selectionNote };
}
