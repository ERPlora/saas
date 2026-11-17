<script setup lang="ts">
import { HubIcon } from '@erplora/ui/shell';
import { IonItem, IonLabel, IonList } from '@ionic/vue';
import { computed, useId } from 'vue';

const props = defineProps<{
  lines: { kind: 'feature' | 'apps' | 'quota' | 'domain'; text: string }[];
}>();
const expanded = defineModel<boolean>('expanded', { default: false });
const listId = `plan-features-${useId()}`;
const visibleLines = computed(() => (expanded.value ? props.lines : props.lines.slice(0, 5)));
</script>

<template>
  <ion-list
    :id="listId"
    lines="none"
    class="plan-features"
  >
    <ion-item
      v-for="(line, index) in visibleLines"
      :key="`${line.kind}-${index}`"
      :data-testid="`plan-${line.kind}`"
    >
      <HubIcon
        slot="start"
        name="ion:checkmark-outline"
        aria-hidden="true"
      />
      <ion-label class="ion-text-wrap">
        {{ line.text }}
      </ion-label>
    </ion-item>
  </ion-list>
  <div class="plan-features__disclosure">
    <button
      v-if="lines.length > 5"
      type="button"
      class="plan-features__toggle"
      :aria-expanded="expanded"
      :aria-controls="listId"
      data-testid="plan-features-toggle"
      @click="expanded = !expanded"
    >
      <HubIcon
        :name="expanded ? 'ion:chevron-up-outline' : 'ion:chevron-down-outline'"
        aria-hidden="true"
      />
      {{ expanded ? $t('billing.plans.showFewer') : $t('billing.plans.showAll') }}
    </button>
  </div>
</template>

<style scoped>
.plan-features {
  grid-row: 5;
  min-inline-size: 0;
  margin: 0;
  padding: 0;
  background: transparent;
}
.plan-features ion-item {
  --background: transparent;
  --min-height: 0;
  --padding-start: 0;
  --inner-padding-end: 0;
  --padding-top: 3px;
  --padding-bottom: 3px;
  font-size: 0.9rem;
}
.plan-features ion-item ion-label {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.4;
  text-wrap: pretty;
  color: var(--ion-text-color);
}
.plan-features ion-icon {
  margin: 2px 8px 0 0;
  align-self: flex-start;
  font-size: 16px;
  color: var(--ep-success-text, var(--ion-color-success));
}
.plan-features__disclosure {
  grid-row: 6;
  min-block-size: 32px;
}
.plan-features__toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-block-size: 32px;
  margin: 0;
  padding: 0 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ep-primary-text, var(--ion-color-primary));
  font: inherit;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}
.plan-features__toggle ion-icon {
  margin: 0;
  font-size: 1.1em;
  color: currentcolor;
}
.plan-features__toggle:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}
@media (max-width: 640px), (pointer: coarse) {
  .plan-features__disclosure,
  .plan-features__toggle {
    min-block-size: 44px;
  }
}
</style>
