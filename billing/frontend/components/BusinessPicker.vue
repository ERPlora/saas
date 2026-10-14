<script setup lang="ts">
// «Which business is it for?» (mockups `store.html`): each business has its own plan and modules, with one
// invoice a month, so the Store sells to the one chosen here. An `ion-select` (never a native select),
// outlined in `md` (`fill="outline"` paints nothing in `ios`), each option the business and its plan.
import { IonCard, IonCardContent, IonSelect, IonSelectOption } from '@ionic/vue';

import type { BusinessRowOut } from '../../../frontend/sdk-types';

defineProps<{
  /** The businesses the account buys for (it owns them). */
  businesses: BusinessRowOut[];
}>();

const chosen = defineModel<string>({ required: true });
</script>

<template>
  <ion-card class="store-picker">
    <ion-card-content class="ion-padding store-picker__content">
      <div class="store-picker__text">
        <h2 class="card-title">
          {{ $t('billing.picker.heading') }}
        </h2>
        <p class="card-text">
          {{ $t('billing.picker.body') }}
        </p>
      </div>
      <ion-select
        class="store-picker__select"
        mode="md"
        fill="outline"
        interface="popover"
        label-placement="floating"
        :label="$t('billing.picker.label')"
        :value="chosen"
        data-testid="store-business"
        @ion-change="chosen = String($event.detail.value)"
      >
        <ion-select-option
          v-for="business in businesses"
          :key="business.id"
          :value="business.id"
        >
          {{ business.plan ? $t('billing.picker.option', { name: business.name, plan: business.plan.name }) : business.name }}
        </ion-select-option>
      </ion-select>
    </ion-card-content>
  </ion-card>
</template>

<style scoped>
.store-picker {
  margin: 0;
}
.store-picker__content {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 24px;
}
.store-picker__text {
  flex: 1 1 260px;
  min-width: 0;
}
.store-picker__select {
  flex: 0 1 320px;
  min-width: 220px;
}
.card-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.card-text {
  margin: 4px 0 0;
  font-size: 0.88rem;
  line-height: 1.45;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
@media (max-width: 599px) {
  .store-picker__select {
    flex: 1 1 100%;
  }
}
</style>
