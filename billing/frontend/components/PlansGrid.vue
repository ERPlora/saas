<script setup lang="ts">
import { shallowRef } from 'vue';

import type { BillingInterval, PlanOut, StoreSubscriptionOut } from '../../../frontend/sdk-types';
import type { Block } from '../store';
import PlanCard from './PlanCard.vue';

defineProps<{
  plans: PlanOut[];
  period: BillingInterval;
  subscription: StoreSubscriptionOut | null;
  block: Block | null;
  scheduledPlanName?: string;
}>();

const emit = defineEmits<{
  upgrade: [plan: PlanOut, period: BillingInterval];
  change: [plan: PlanOut, period: BillingInterval];
  switch: [period: BillingInterval];
  downgrade: [];
  keep: [];
}>();

const expanded = shallowRef(false);
</script>

<template>
  <div class="plans-grid">
    <PlanCard
      v-for="plan in plans"
      :key="plan.slug"
      v-model:expanded="expanded"
      :plan="plan"
      :period="period"
      :subscription="subscription"
      :block="block"
      :scheduled-plan-name="scheduledPlanName"
      @upgrade="emit('upgrade', plan, $event)"
      @change="emit('change', plan, $event)"
      @switch="emit('switch', $event)"
      @downgrade="emit('downgrade')"
      @keep="emit('keep')"
    />
  </div>
</template>

<style scoped>
.plans-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  column-gap: 20px;
  row-gap: 12px;
  align-items: stretch;
  inline-size: 100%;
  max-inline-size: 1120px;
  margin-inline: auto;
}
.plans-grid > * {
  min-inline-size: 0;
}
@media (min-width: 640px) {
  .plans-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (min-width: 640px) and (max-width: 1099px) {
  .plans-grid:has(> :nth-child(2)) > :last-child:nth-child(odd) {
    grid-column: 1 / -1;
    justify-self: center;
    inline-size: calc((100% - 20px) / 2);
  }
}
@media (min-width: 1100px) {
  .plans-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
