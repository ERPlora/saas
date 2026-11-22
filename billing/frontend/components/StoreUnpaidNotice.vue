<script setup lang="ts">
// The Store's notice of a business with an unpaid invoice: it blocks what charges for THAT business, and says why
// and where to pay. A declined card cannot pay it: only «Go to Billing» until the card changes.
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

import { BILLING } from '../../../accounts/frontend/paths';
import type { BusinessRowOut } from '../../../frontend/sdk-types/hubs';
import type { Block } from '../store';

defineProps<{
  business: BusinessRowOut;
  block: Block;
}>();
</script>

<template>
  <InlineFeedback
    tone="danger"
    icon="ion:card-outline"
    role="alert"
    :heading="$t('billing.unpaid.heading', { name: business.name })"
    data-testid="store-unpaid"
  >
    {{ $t(`billing.unpaid.${block}`) }}
    <template #actions>
      <ion-button
        v-if="business.pay_url && block !== 'card_declined'"
        size="small"
        :href="business.pay_url"
        data-testid="store-unpaid-pay"
      >
        <HubIcon
          slot="start"
          name="ion:card-outline"
          aria-hidden="true"
        />
        {{ $t('billing.unpaid.pay') }}
      </ion-button>
      <ion-button
        size="small"
        fill="outline"
        :router-link="`${BILLING}?business=${business.id}`"
        data-testid="store-unpaid-billing"
      >
        <HubIcon
          slot="start"
          name="ion:receipt-outline"
          aria-hidden="true"
        />
        {{ $t('billing.unpaid.billing') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>

<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
