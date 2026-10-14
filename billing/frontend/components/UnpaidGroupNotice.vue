<script setup lang="ts">
// Two or more invoices Stripe could not charge, on top of Invoices, in ONE banner (mockups `billing.html`
// «past-due-two»; audit 2026-10-14, R-15: one banner per business took half the page at 1024 px). One invoice
// keeps its own banner (UnpaidInvoiceNotice).
//   - the heading says how many and how much in all («2 unpaid invoices: €72.58»);
//   - each business on its own line, the suspended ones first: suspended until it is paid, or the day it is
//     suspended if not paid (7 days of grace, `graceEnd`), with its amount; days, never the hour;
//   - on the web each line has its action: «Pay the invoice» (PayInvoiceButton); after a declined card
//     «Change card» (Stripe's Customer Portal) leads and «Pay» waits, described by why. Another account
//     paying the business: only why;
//   - inside the apps, no button nor link: where to pay them (README §4).
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon, useSurface, WebOnly } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, useId } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatDate } from '../format';
import { formatAmount, graceEnd } from '../invoices';
import { useCardPortal } from '../portal';
import type { UnpaidItem } from '../unpaid';
import PayInvoiceButton from './PayInvoiceButton.vue';

const props = defineProps<{
  /** The invoices not collected, each with its business as the account's list has it. */
  items: UnpaidItem[];
}>();

const { t, locale } = useI18n();
const portal = useCardPortal();
const { isWeb } = useSurface();
const uid = useId();

const heading = computed(() => {
  const count = props.items.length;
  const cents = props.items.reduce((sum, item) => sum + item.invoice.total_cents, 0);
  const amount = formatAmount(cents, props.items[0]?.invoice.currency ?? '', locale.value);
  return t('billing.notice.groupHeading', { count, amount }, count);
});

const isSuspended = (item: UnpaidItem) => item.business?.status === 'suspended';

const lines = computed(() =>
  [...props.items]
    .sort((a, b) => Number(isSuspended(b)) - Number(isSuspended(a)))
    .map((item) => {
      const { invoice, business } = item;
      const date = formatDate(graceEnd(business?.unpaid_since), locale.value);
      let key = 'billing.notice.groupPastDueNoDate';
      if (isSuspended(item)) key = 'billing.notice.groupSuspended';
      else if (date) key = 'billing.notice.groupPastDue';
      return {
        id: invoice.id,
        invoice,
        key,
        name: invoice.business.name,
        date,
        amount: formatAmount(invoice.total_cents, invoice.currency, locale.value),
        declined: invoice.pay_blocked_reason === 'card_change_required',
        payerElsewhere: invoice.pay_blocked_reason === 'payer_required',
        hubId: invoice.business.id ?? business?.id ?? null,
        whyId: `unpaid-group-why-${uid}-${invoice.id}`,
      };
    }),
);

const anyDeclined = computed(() => lines.value.some((line) => line.declined));
</script>

<template>
  <InlineFeedback
    tone="danger"
    icon="lucide:credit-card"
    role="alert"
    :heading="heading"
  >
    <ul class="unpaid-group">
      <li
        v-for="line in lines"
        :key="line.id"
        class="unpaid-group__item"
        data-testid="unpaid-group-item"
        :data-id="line.id"
      >
        <div class="unpaid-group__info">
          <span
            class="unpaid-group__text"
            data-testid="unpaid-group-text"
          ><i18n-t
            :keypath="line.key"
            tag="span"
          >
            <template #name><strong>{{ line.name }}</strong></template>
            <template #date>{{ line.date }}</template>
            <template #amount>{{ line.amount }}</template>
          </i18n-t>{{ line.declined ? ` ${$t('billing.notice.declined')}` : '' }}</span>
          <WebOnly>
            <span
              v-if="line.declined || line.payerElsewhere"
              :id="line.whyId"
              class="unpaid-group__why"
              data-testid="unpaid-group-why"
            >{{ line.declined ? $t('billing.notice.changeFirst') : $t('billing.notice.payerRequired') }}</span>
          </WebOnly>
        </div>
        <!-- Web only (README §4): inside the apps the actions are not even there. -->
        <div
          v-if="isWeb && !line.payerElsewhere"
          class="unpaid-group__actions"
        >
          <ion-button
            v-if="line.declined && line.hubId"
            size="small"
            data-testid="unpaid-group-change-card"
            :disabled="!!portal.opening.value"
            @click="line.hubId && portal.open(line.hubId)"
          >
            <ion-spinner
              v-if="portal.opening.value === line.hubId"
              slot="start"
              name="crescent"
              aria-hidden="true"
            />
            <HubIcon
              v-else
              slot="start"
              name="lucide:credit-card"
              aria-hidden="true"
            />
            {{ $t('billing.notice.changeCard') }}
          </ion-button>
          <PayInvoiceButton
            size="small"
            :invoice="line.invoice"
            :fill="line.declined ? 'outline' : 'solid'"
            :described-by="line.declined ? line.whyId : undefined"
          />
        </div>
      </li>
    </ul>
    <span
      class="unpaid-group__footer"
      data-testid="unpaid-group-footer"
    >{{ $t('billing.notice.groupFooter') }}</span>
    <WebOnly>
      <template #app>
        <span
          class="unpaid-group__why"
          data-testid="unpaid-group-app"
        >{{ anyDeclined ? $t('billing.notice.appDeclinedMany') : $t('billing.notice.appMany') }}</span>
      </template>
    </WebOnly>
  </InlineFeedback>
</template>

<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
<style scoped>
.unpaid-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 4px 0 6px;
  padding: 0;
  list-style: none;
}
.unpaid-group__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 12px;
}
.unpaid-group__info {
  display: flex;
  flex: 1 1 16rem;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.unpaid-group__why {
  display: block;
  font-size: 0.85rem;
}
.unpaid-group__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.unpaid-group__actions ion-button {
  margin: 0;
  white-space: nowrap;
  text-transform: none;
}
/* A real tap target on a phone (audit 2026-10-14, R-13). */
@media (max-width: 640px) {
  .unpaid-group__actions ion-button {
    min-height: 44px;
  }
}
</style>
