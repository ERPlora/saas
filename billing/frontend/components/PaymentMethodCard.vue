<script setup lang="ts">
// Billing → Payment details: the card of one payer (mockups `billing.html` «payment»; README §4 and §6.18;
// `billing.payment_method.get`): brand and last four, when it expires and which businesses it pays; the last
// charge that failed, with its date and business; on the web «Change card» — Stripe's Customer Portal,
// «the secure payment page», the main action after a failure (`portal.ts`). Inside the apps, how to change
// it, without a button nor a link (README §4). Stripe away, or no card yet: it says so.
import { StatusPill } from '@erplora/ui/components';
import { HubIcon, WebOnly } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { PaymentMethodRowOut } from '../../../frontend/sdk-types';
import { formatDate } from '../format';
import { cardBrand } from '../invoices';
import { useCardPortal } from '../portal';

const props = defineProps<{
  method: PaymentMethodRowOut;
}>();

const { t, locale } = useI18n();
const portal = useCardPortal();

const hubId = computed(() => props.method.businesses.find((business) => business.id)?.id ?? null);
const businesses = computed(() =>
  new Intl.ListFormat(locale.value, { style: 'long', type: 'conjunction' }).format(props.method.businesses.map((business) => business.name)),
);
const title = computed(() => {
  const card = props.method.card;
  return card ? t('billing.payment.method.card', { brand: cardBrand(card.brand), last4: card.last4 }) : t('billing.payment.method.none');
});
const detail = computed(() => {
  const card = props.method.card;
  if (props.method.unavailable) return t('billing.payment.method.unavailable');
  if (!card) return t('billing.payment.method.pays', { businesses: businesses.value });
  return t('billing.payment.method.expires', {
    month: String(card.exp_month).padStart(2, '0'),
    year: String(card.exp_year).slice(-2),
    businesses: businesses.value,
  });
});
const failure = computed(() => {
  const last = props.method.last_failure;
  return last ? t('billing.payment.method.failedWhen', { date: formatDate(last.at, locale.value), business: last.business }) : '';
});
</script>

<template>
  <ion-card>
    <ion-card-content class="ion-padding">
      <div class="page-eyebrow">
        {{ $t('billing.payment.method.title') }}
      </div>
      <div class="payment-row">
        <span class="payment-icon"><HubIcon
          name="lucide:credit-card"
          aria-hidden="true"
        /></span>
        <div>
          <h2
            v-if="!method.unavailable"
            class="card-title"
            data-testid="payment-card"
          >
            {{ title }}
          </h2>
          <p
            class="card-text small"
            data-testid="payment-card-detail"
          >
            {{ detail }}
          </p>
        </div>
      </div>
      <p
        v-if="method.last_failure"
        class="payment-failed"
        data-testid="payment-failed"
      >
        <StatusPill
          tone="danger"
          size="sm"
          :label="$t('billing.payment.method.failed')"
        />
        <span class="card-text small">{{ failure }}</span>
      </p>
      <WebOnly>
        <div
          v-if="hubId"
          class="card-actions"
        >
          <ion-button
            data-testid="payment-change"
            :fill="method.last_failure ? 'solid' : 'outline'"
            :disabled="!!portal.opening.value"
            @click="hubId && portal.open(hubId)"
          >
            <ion-spinner
              v-if="portal.opening.value"
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
            {{ $t('billing.payment.method.change') }}
          </ion-button>
        </div>
        <p
          class="card-text small"
          data-testid="payment-secure"
        >
          {{ $t('billing.payment.method.secure') }}
        </p>
        <template #app>
          <p
            class="card-text small"
            data-testid="payment-app"
          >
            {{ $t('billing.payment.method.app') }}
          </p>
        </template>
      </WebOnly>
    </ion-card-content>
  </ion-card>
</template>

<style scoped src="../../../hubs/frontend/components/panel-card.css"></style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
<style scoped>
.payment-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.payment-icon {
  display: grid;
  place-items: center;
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  font-size: 20px;
  color: var(--ion-color-primary);
  background: color-mix(in oklab, var(--ion-color-primary) 10%, transparent);
}
.payment-failed {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 12px 0 0;
}
.payment-failed .card-text {
  margin: 0;
}
</style>
