<script setup lang="ts">
// «Pay the invoice · 36,29 €» (mockups `billing.html` «past-due» → «paying»; README §6.18 and §6.20): blue,
// not red — paying is the good action. Disabled while the server says «Pay» waits (a declined card to
// change first, or another account pays the business), described by the reason the page shows next to it
// (`describedBy`), and while any payment of the page runs; «Paying…» from the press until the page leaves
// for Stripe (`pay.ts`). Web only: the page renders it in `<WebOnly>`.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { InvoiceRowOut } from '../../../frontend/sdk-types';
import { formatAmount } from '../invoices';
import { usePayInvoice } from '../pay';

const props = withDefaults(
  defineProps<{
    invoice: Pick<InvoiceRowOut, 'id' | 'total_cents' | 'currency' | 'can'>;
    /** `solid` when it is the notice's main action; `outline` while it waits for another card. */
    fill?: 'solid' | 'outline';
    /** The id of the sentence that says why it waits. */
    describedBy?: string;
  }>(),
  { fill: 'solid', describedBy: undefined },
);

const { locale } = useI18n();
const { pay, paying } = usePayInvoice();

const mine = computed(() => paying.value === props.invoice.id);
const disabled = computed(() => !props.invoice.can.pay || !!paying.value);
const amount = computed(() => formatAmount(props.invoice.total_cents, props.invoice.currency, locale.value));

function press(): void {
  if (!disabled.value) void pay(props.invoice);
}
</script>

<template>
  <ion-button
    data-testid="pay-invoice"
    :fill="fill"
    :disabled="disabled"
    :aria-describedby="describedBy"
    @click="press"
  >
    <ion-spinner
      v-if="mine"
      slot="start"
      name="crescent"
      aria-hidden="true"
    />
    <HubIcon
      v-else
      slot="start"
      name="ion:card-outline"
      aria-hidden="true"
    />
    {{ mine ? $t('billing.notice.paying') : $t('billing.notice.pay', { amount }) }}
  </ion-button>
</template>

<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
