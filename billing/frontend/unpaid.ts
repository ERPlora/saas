// What waits for a payment: each business of the account with an unpaid invoice (payment pending or suspended), live,
// with its oldest invoice Stripe could not charge when the account sees it (its owner or its payer). A credit note is
// no debt.
//
// Both lists come in the same stream and are read as one (`useLiveState`): `items` stays `undefined` until both
// answered, so nothing shows without its amount, and `state` tells «nothing owed» (`empty`) from «could not check»
// (`error`: a query or the stream failed, or nothing came in time).
//
// «Invoice paid»: when an invoice leaves the open ones — paid here, in another tab, or at Stripe's page — it is
// asked again (`billing.invoice.get`) and, paid, a toast says its business is up to date. The invoice the
// page went to pay at Stripe (`pay.ts`) is watched from the first answer on, so coming back to a page
// that never saw it unpaid still says it; once said, it is forgotten.
import { toastSuccess } from '@erplora/ui/shell';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useLiveState } from '../../frontend/live-state';
import type { BusinessListOut, BusinessRowOut, InvoiceListOut, InvoiceRowOut } from '../../frontend/sdk-types';
import { forgetPayment, rememberedPayment } from './pay';

export interface UnpaidItem {
  business: BusinessRowOut;
  /** Its oldest invoice not collected; `null` when the account does not see it. */
  invoice: InvoiceRowOut | null;
}

/** As many as the account may owe at once: one per business. */
const LIMIT = 100;

const isUnpaid = (business: BusinessRowOut) => business.status === 'past_due' || business.status === 'suspended';

/** The oldest invoice not collected of each business: its grace counts from it. */
function oldestByBusiness(rows: readonly InvoiceRowOut[]): Map<string, InvoiceRowOut> {
  const oldest = new Map<string, InvoiceRowOut>();
  for (const invoice of rows) {
    const id = invoice.business.id;
    if (invoice.kind !== 'invoice' || !id) continue;
    const kept = oldest.get(id);
    if (!kept || invoice.date < kept.date) oldest.set(id, invoice);
  }
  return oldest;
}

function unpaidItems(open: InvoiceListOut, list: BusinessListOut): UnpaidItem[] {
  const invoices = oldestByBusiness(open.rows);
  return list.rows.filter(isUnpaid).map((business) => ({ business, invoice: invoices.get(business.id) ?? null }));
}

export function useUnpaidInvoices() {
  const client = useLiveClient();
  const { t } = useI18n();
  const open = useLive('billing.invoice.list', { status: 'open', limit: LIMIT });
  const list = useLive('hubs.business.list', { limit: LIMIT });
  const both = {
    data: computed(() => (open.data.value && list.data.value ? unpaidItems(open.data.value, list.data.value) : undefined)),
    status: computed(() => (open.status.value === 'error' ? open.status.value : list.status.value)),
    error: computed(() => open.error.value ?? list.error.value),
    // One stream carries both: reopening it asks both again.
    refresh: open.refresh,
  };
  const state = useLiveState(both, { client });

  /** What was unpaid at the last answer; `null` before the first one. */
  let watched: Set<string> | null = null;
  watch(
    () => open.data.value,
    (data) => {
      if (!data) return;
      const now = new Set(data.rows.map((row) => row.id));
      const before = watched ?? new Set<string>();
      const remembered = rememberedPayment();
      if (watched === null && remembered) before.add(remembered);
      watched = now;
      for (const id of before) if (!now.has(id)) void sayPaid(id);
    },
  );

  async function sayPaid(id: string): Promise<void> {
    try {
      const invoice = await client.api.call('billing.invoice.get', { id });
      if (invoice.payment_status === 'paid') toastSuccess(t('billing.notice.paid', { name: invoice.business.name }));
    } catch (error) {
      console.error('billing: an invoice that left the unpaid ones could not be read', error);
    } finally {
      if (rememberedPayment() === id) forgetPayment();
    }
  }

  return { items: both.data, state };
}
