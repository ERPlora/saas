// What waits for a payment in the Billing section (mockups `billing.html`; README §6.18; PLAN-SAAS §3.3):
// the account's invoices Stripe could not charge (`billing.invoice.list` with `status=open`, live), each
// with its business as the account's list has it (`hubs.business.list`, live: whether it is suspended,
// since when, whether the card changed). A credit note is no debt.
//
// «Invoice paid»: when an invoice leaves that list — paid here, in another tab, or at Stripe's page — it is
// asked again (`billing.invoice.get`) and, paid, a toast says its business is up to date. The invoice the
// page went to pay at Stripe (`pay.ts`) is watched from the first answer on, so coming back to a page
// that never saw it unpaid still says it; once said, it is forgotten.
import { toastSuccess } from '@erplora/ui/shell';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessRowOut, InvoiceRowOut } from '../../frontend/sdk-types';
import { forgetPayment, rememberedPayment } from './pay';

export interface UnpaidItem {
  invoice: InvoiceRowOut;
  /** Its business in the account's list; `null` when it is gone or not listed. */
  business: BusinessRowOut | null;
}

/** As many as the account may owe at once: one per business. */
const LIMIT = 100;

export function useUnpaidInvoices() {
  const client = useLiveClient();
  const { t } = useI18n();
  const open = useLive('billing.invoice.list', { status: 'open', limit: LIMIT });
  const list = useLive('hubs.business.list', { limit: LIMIT });

  const businesses = computed(() => new Map((list.data.value?.rows ?? []).map((row) => [row.id, row])));
  const items = computed<UnpaidItem[]>(() =>
    (open.data.value?.rows ?? [])
      .filter((invoice) => invoice.kind === 'invoice')
      .map((invoice) => ({ invoice, business: (invoice.business.id && businesses.value.get(invoice.business.id)) || null })),
  );

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
      if (invoice.payment_status === 'paid') void toastSuccess(t('billing.notice.paid', { name: invoice.business.name }));
    } catch (error) {
      console.error('billing: an invoice that left the unpaid ones could not be read', error);
    } finally {
      if (rememberedPayment() === id) forgetPayment();
    }
  }

  return { items, status: open.status };
}
