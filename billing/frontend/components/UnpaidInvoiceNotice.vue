<script setup lang="ts">
// The banner of an invoice Stripe could not charge, on top of Invoices (mockups `billing.html` «past-due»,
// «suspended-norte», «card-updated»; README §4, §6.18 and §6.20; PLAN-SAAS §3.3 and §3.6 point 11):
//   - how much, of which business, which invoice and of when; until when the business still works (7 days
//     of grace from the invoice) or that it is suspended and nothing is deleted;
//   - on the web, «Pay the invoice» is the main action (PayInvoiceButton). After a declined card «Change
//     card» is (Stripe's Customer Portal) and «Pay» waits, described by why; once the card changed
//     (`unpaid_reason = card_changed`), the banner says so and «Pay» is back. Another account paying the
//     business: only why;
//   - inside the apps, how to pay it, without a button nor a link (README §4).
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon, useSurface, WebOnly } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, useId } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessRowOut, InvoiceRowOut } from '../../../frontend/sdk-types';
import { formatDate } from '../format';
import { formatAmount, graceEnd, invoiceName } from '../invoices';
import { useCardPortal } from '../portal';
import PayInvoiceButton from './PayInvoiceButton.vue';

const props = defineProps<{
  invoice: InvoiceRowOut;
  /** The business as the account's list has it (its status and since when it is unpaid); `null` when gone. */
  business: Pick<BusinessRowOut, 'id' | 'status' | 'unpaid_reason' | 'unpaid_since'> | null;
}>();

const { t, locale } = useI18n();
const portal = useCardPortal();
/** The account the app opens in the browser says why it pays nothing, not where (audit 2 S-09). */
const { isWeb, surface } = useSurface();
const whyId = `unpaid-why-${useId()}`;

const name = computed(() => props.invoice.business.name);
const amount = computed(() => formatAmount(props.invoice.total_cents, props.invoice.currency, locale.value));
const declined = computed(() => props.invoice.pay_blocked_reason === 'card_change_required');
const payerElsewhere = computed(() => props.invoice.pay_blocked_reason === 'payer_required');
const suspended = computed(() => props.business?.status === 'suspended');
const cardChanged = computed(() => !declined.value && props.invoice.can.pay && props.business?.unpaid_reason === 'card_changed');
const hubId = computed(() => props.invoice.business.id ?? props.business?.id ?? null);

const heading = computed(() => {
  if (cardChanged.value) return t('billing.notice.cardChangedHeading');
  const values = { amount: amount.value, name: name.value };
  return suspended.value ? t('billing.notice.suspendedHeading', values) : t('billing.notice.pastDueHeading', values);
});

const body = computed(() => {
  if (cardChanged.value) return t('billing.notice.cardChangedBody', { name: name.value, amount: amount.value });
  const values = { invoice: invoiceName(props.invoice), date: formatDate(props.invoice.date, locale.value, 'UTC') };
  const until = formatDate(graceEnd(props.business?.unpaid_since), locale.value);
  let text: string;
  if (suspended.value) text = t('billing.notice.suspendedBody', values);
  else if (until) text = t('billing.notice.pastDueBody', { ...values, until });
  else text = t('billing.notice.pastDueBodyNoDate', values);
  return declined.value ? `${t('billing.notice.declined')} ${text}` : text;
});
</script>

<template>
  <InlineFeedback
    :tone="cardChanged ? 'success' : 'danger'"
    :icon="cardChanged ? 'ion:checkmark-circle-outline' : 'lucide:credit-card'"
    :heading="heading"
    :role="cardChanged ? 'status' : 'alert'"
  >
    <span data-testid="unpaid-body">{{ body }}</span>
    <WebOnly>
      <span
        v-if="declined || payerElsewhere"
        :id="whyId"
        class="unpaid-why"
        data-testid="unpaid-why"
      >{{ declined ? $t('billing.notice.changeFirst') : $t('billing.notice.payerRequired') }}</span>
      <template #app>
        <span
          class="unpaid-why"
          data-testid="unpaid-app"
        >{{ surface === 'account' ? $t('billing.notice.account') : declined ? $t('billing.notice.appDeclined') : $t('billing.notice.app') }}</span>
      </template>
    </WebOnly>
    <!-- Web only (README §4): inside the apps the actions are not even there. -->
    <template
      v-if="isWeb && !payerElsewhere"
      #actions
    >
      <!-- Its own wrapping row: on a phone the two buttons stack instead of squeezing. -->
      <div class="unpaid-actions">
        <ion-button
          v-if="declined && hubId"
          data-testid="unpaid-change-card"
          :disabled="!!portal.opening.value"
          @click="hubId && portal.open(hubId)"
        >
          <ion-spinner
            v-if="portal.opening.value === hubId"
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
          :invoice="invoice"
          :fill="declined ? 'outline' : 'solid'"
          :described-by="declined ? whyId : undefined"
        />
      </div>
    </template>
  </InlineFeedback>
</template>

<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
<style scoped>
.unpaid-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.unpaid-actions ion-button {
  margin: 0;
  white-space: nowrap;
}
.unpaid-why {
  display: block;
  margin-top: 4px;
  font-size: 0.85rem;
}
</style>
