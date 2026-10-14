<script setup lang="ts">
// Billing → Payment details (mockups `billing.html` «payment», «empty», «loading», «error»; README §3 and §4):
// per payer of the account (`billing.payment_method.get`: asked to Stripe when the tab opens, kept a few
// minutes by the server; not live), its card (PaymentMethodCard: «Change card» on the web) next to its
// billing details (BillingProfileCard: editable everywhere). Without any payment yet, what the first one
// asks for. Loading and failing say so; «Retry» asks again.
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSkeletonText } from '@ionic/vue';
import { shallowRef } from 'vue';

import type { PaymentMethodRowOut } from '../../../frontend/sdk-types';
import BillingProfileCard from './BillingProfileCard.vue';
import PaymentMethodCard from './PaymentMethodCard.vue';

const client = useLiveClient();
const methods = shallowRef<PaymentMethodRowOut[] | null>(null);
const failed = shallowRef(false);

async function load(): Promise<void> {
  failed.value = false;
  methods.value = null;
  try {
    methods.value = (await client.api.call('billing.payment_method.get')).methods;
  } catch (error) {
    console.error('billing: the payment methods could not be loaded', error);
    failed.value = true;
  }
}
void load();
</script>

<template>
  <div class="payment">
    <InlineFeedback
      v-if="failed"
      tone="danger"
      role="alert"
      :heading="$t('billing.payment.loadError')"
      data-testid="payment-error"
    >
      {{ $t('billing.payment.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="payment-retry"
          @click="load"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
            aria-hidden="true"
          />
          {{ $t('billing.payment.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <div
      v-else-if="!methods"
      class="card-grid"
      aria-busy="true"
      data-testid="payment-loading"
    >
      <ion-card
        v-for="card in 2"
        :key="card"
      >
        <ion-card-content class="ion-padding">
          <ion-skeleton-text
            animated
            style="width: 40%; height: 12px"
          />
          <ion-skeleton-text
            animated
            style="width: 70%; height: 20px; margin-top: 14px"
          />
          <ion-skeleton-text
            animated
            style="width: 50%; height: 14px; margin-top: 10px"
          />
        </ion-card-content>
      </ion-card>
    </div>

    <div
      v-else-if="methods.length === 0"
      class="card-grid"
    >
      <ion-card data-testid="payment-method-empty">
        <ion-card-content class="ion-padding">
          <div class="page-eyebrow">
            {{ $t('billing.payment.method.title') }}
          </div>
          <p class="card-text">
            {{ $t('billing.payment.method.empty') }}
          </p>
        </ion-card-content>
      </ion-card>
      <ion-card data-testid="payment-profile-empty">
        <ion-card-content class="ion-padding">
          <div class="page-eyebrow">
            {{ $t('billing.payment.profile.title') }}
          </div>
          <p class="card-text">
            {{ $t('billing.payment.profile.empty') }}
          </p>
        </ion-card-content>
      </ion-card>
    </div>

    <template v-else>
      <div
        v-for="method in methods"
        :key="method.businesses.map((business) => business.id ?? business.name).join()"
        class="card-grid"
      >
        <PaymentMethodCard :method="method" />
        <BillingProfileCard :businesses="method.businesses" />
      </div>
    </template>
  </div>
</template>

<style scoped src="../../../hubs/frontend/components/panel-card.css"></style>
<style scoped>
.payment {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: 16px;
}
.card-text {
  margin-top: 12px;
}
</style>
