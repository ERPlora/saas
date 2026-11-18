<script setup lang="ts">
import { AlignedCardGrid } from '@erplora/ui/components';
import { shallowRef } from 'vue';

import type { PlanOut } from '../../../frontend/sdk-types/hubs-catalog';
import type { BillingInterval, StoreSubscriptionOut } from '../../../frontend/sdk-types/store';
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
  <AlignedCardGrid
    class="plans-grid"
    :rows="7"
  >
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
  </AlignedCardGrid>
</template>
