<script setup lang="ts">
// The way out of an unpaid invoice wherever a business is listed (audit 2026-10-14, R-07 and R-09; mockups
// `launch.html` «past-due», `businesses.html`): on the web, for whoever may pay it (`pay_url`, its owner),
// «Pay the invoice» goes to Stripe's page. After a declined card «Change card» (Stripe's Customer Portal,
// `useCardPortal`, as on Billing) is the main action and «Pay» waits for it, as Billing does. Inside the apps
// nothing at all (README §4): the notice says where to pay. In a list each button is named with its business.
import { HubIcon, WebOnly } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import { useCardPortal } from '../../../billing/frontend/portal';
import type { BusinessRowOut } from '../../../frontend/sdk-types';

const props = withDefaults(
  defineProps<{
    business: Pick<BusinessRowOut, 'id' | 'name' | 'unpaid_reason' | 'pay_url'>;
    /** In a list: each button's accessible name says its business. */
    named?: boolean;
    /** The main button's size (the launcher's is large). */
    size?: 'small' | 'default' | 'large';
    /** `block` in a card that stacks its actions. */
    expand?: 'block';
    /** Not the most urgent of a list: every button outlined, so one business leads (audit 2 S-06). */
    secondary?: boolean;
  }>(),
  { named: false, size: 'default', expand: undefined, secondary: false },
);

const portal = useCardPortal();
const declined = computed(() => props.business.unpaid_reason === 'card_declined');
</script>

<template>
  <WebOnly>
    <div
      v-if="business.pay_url"
      class="unpaid-actions"
      :class="{ 'is-block': expand === 'block' }"
    >
      <ion-button
        v-if="declined"
        data-testid="unpaid-change-card"
        :fill="secondary ? 'outline' : 'solid'"
        :size="size === 'default' ? undefined : size"
        :expand="expand"
        :aria-label="named ? $t('hubs.unpaid.changeCardName', { name: business.name }) : undefined"
        :disabled="!!portal.opening.value"
        @click="portal.open(business.id)"
      >
        <ion-spinner
          v-if="portal.opening.value === business.id"
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
        {{ $t('hubs.unpaid.changeCard') }}
      </ion-button>
      <ion-button
        data-testid="unpaid-pay"
        :fill="declined || secondary ? 'outline' : 'solid'"
        :size="size === 'default' || (declined && size === 'large') ? undefined : size"
        :expand="expand"
        :href="business.pay_url"
        :disabled="declined"
        :aria-label="named ? $t('hubs.unpaid.payName', { name: business.name }) : undefined"
      >
        <HubIcon
          slot="start"
          name="ion:card-outline"
          aria-hidden="true"
        />
        {{ $t('hubs.unpaid.pay') }}
      </ion-button>
    </div>
  </WebOnly>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
.unpaid-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.unpaid-actions ion-button {
  margin: 0;
  min-height: 44px;
  white-space: nowrap;
}
.unpaid-actions.is-block {
  flex-direction: column;
  gap: 10px;
}
</style>
