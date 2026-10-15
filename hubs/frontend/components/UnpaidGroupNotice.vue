<script setup lang="ts">
// Several businesses with an unpaid invoice (audit 2026-10-14, R-15; mockups `businesses.html`, «2 negocios
// tienen facturas sin pagar»): ONE notice instead of one per business, so two of them no longer take half the
// page. The most urgent first (audit 2 S-07, as Billing orders them): the suspended, then the one suspended
// soonest. Each line says its business and its date (the day, never the minute: since when it is suspended, or
// when it will be), what it owes (audit 2 S-08: from the unpaid invoices the account sees, `billing.invoice.list`;
// without them, no amounts) and, on the web, its own way to pay (`UnpaidActions`: «Pay the invoice», or «Change
// card» after a declined card), filled only for the first one (audit 2 S-06). Inside the apps, where to pay,
// without a button (README §4).
import { InlineFeedback } from '@erplora/ui/components';
import { WebOnly } from '@erplora/ui/shell';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatDate } from '../../../billing/frontend/format';
import { formatAmount } from '../../../billing/frontend/invoices';
import { useLiveState } from '../../../frontend/live-state';
import type { BusinessRowOut } from '../../../frontend/sdk-types';
import { unpaidDeadline } from '../business-status';
import UnpaidActions from './UnpaidActions.vue';

type Unpaid = Pick<BusinessRowOut, 'id' | 'name' | 'status' | 'unpaid_reason' | 'unpaid_since' | 'pay_url'>;

const props = defineProps<{
  businesses: Unpaid[];
}>();

const { t, locale } = useI18n();

/** The most urgent first: the suspended, then by the day it was left unpaid (its grace ends first); a business
 *  without that day last. */
const ordered = computed(() =>
  [...props.businesses].sort(
    (a, b) =>
      Number(b.status === 'suspended') - Number(a.status === 'suspended') ||
      (Date.parse(a.unpaid_since ?? '') || Infinity) - (Date.parse(b.unpaid_since ?? '') || Infinity),
  ),
);

/** What each business owes, from the invoices Stripe could not charge that the account sees (owner or payer):
 *  only from a real answer (`useLiveState`); loading or failing, the lines go without amounts. */
const open = useLive('billing.invoice.list', { status: 'open', limit: 100 });
const openState = useLiveState(open, { isEmpty: (data) => data.rows.length === 0 });
const owed = computed(() => {
  const byBusiness = new Map<string, { cents: number; currency: string }>();
  const answered = openState.view.value === 'ready' || openState.view.value === 'empty';
  for (const invoice of answered ? (open.data.value?.rows ?? []) : []) {
    const id = invoice.business.id;
    if (invoice.kind !== 'invoice' || !id) continue;
    const now = byBusiness.get(id);
    byBusiness.set(id, { cents: (now?.cents ?? 0) + invoice.total_cents, currency: invoice.currency });
  }
  return byBusiness;
});
const amountOf = (business: Unpaid) => {
  const debt = owed.value.get(business.id);
  return debt ? formatAmount(debt.cents, debt.currency, locale.value) : '';
};
/** «2 businesses have unpaid invoices: €72.58», when every one of them has its amount. */
const heading = computed(() => {
  const count = props.businesses.length;
  const debts = props.businesses.map((business) => owed.value.get(business.id));
  if (debts.some((debt) => !debt)) return t('hubs.list.unpaid.groupHeading', { count });
  const cents = debts.reduce((sum, debt) => sum + (debt?.cents ?? 0), 0);
  return t('hubs.list.unpaid.groupHeadingAmount', { count, amount: formatAmount(cents, debts[0]?.currency ?? '', locale.value) });
});

function sentence(business: Unpaid): string {
  const since = business.unpaid_since;
  let text: string;
  if (business.status === 'suspended') {
    text = since
      ? t('hubs.list.unpaid.lineSuspendedSince', { name: business.name, date: formatDate(since, locale.value) })
      : t('hubs.list.unpaid.lineSuspended', { name: business.name });
  } else {
    const until = formatDate(unpaidDeadline(since), locale.value);
    text = until
      ? t('hubs.list.unpaid.linePastDueUntil', { name: business.name, date: until })
      : t('hubs.list.unpaid.linePastDue', { name: business.name });
  }
  return business.unpaid_reason === 'card_declined' ? `${text} ${t('hubs.list.unpaid.lineDeclined')}` : text;
}
</script>

<template>
  <InlineFeedback
    tone="danger"
    icon="ion:card-outline"
    :heading="heading"
  >
    <ul class="unpaid-lines">
      <li
        v-for="(business, index) in ordered"
        :key="business.id"
        class="unpaid-line"
        data-testid="businesses-unpaid-line"
      >
        <span class="unpaid-line__text">{{ sentence(business) }}</span>
        <strong
          v-if="amountOf(business)"
          class="unpaid-line__amount"
          data-testid="businesses-unpaid-amount"
        >{{ amountOf(business) }}</strong>
        <UnpaidActions
          :business="business"
          named
          size="small"
          :secondary="index > 0"
        />
      </li>
    </ul>
    <span class="unpaid-foot">{{ $t('hubs.list.unpaid.nothingDeleted') }}</span>
    <WebOnly>
      <template #app>
        <span
          class="unpaid-foot"
          data-testid="unpaid-app"
        >{{ $t('hubs.unpaid.app') }}</span>
      </template>
    </WebOnly>
  </InlineFeedback>
</template>

<style scoped>
.unpaid-lines {
  display: grid;
  gap: 8px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}
.unpaid-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 12px;
}
.unpaid-line__text {
  flex: 1 1 18rem;
  min-width: 0;
}
.unpaid-line__amount {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.unpaid-foot {
  display: block;
  margin-top: 6px;
}
</style>
