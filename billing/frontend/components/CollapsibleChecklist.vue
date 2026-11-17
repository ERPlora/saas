<script setup lang="ts">
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList } from '@ionic/vue';
import { computed, nextTick, onMounted, onUpdated, useId, useTemplateRef } from 'vue';

const props = withDefaults(
  defineProps<{
    items: { text: string; testid?: string }[];
    collapsedCount?: number;
    showAllLabel: string;
    showFewerLabel: string;
    toggleTestid?: string;
  }>(),
  { collapsedCount: 5, toggleTestid: undefined },
);
const expanded = defineModel<boolean>('expanded', { default: false });
const listId = `collapsible-checklist-${useId()}`;
const visibleItems = computed(() => (expanded.value ? props.items : props.items.slice(0, props.collapsedCount)));
const toggle = useTemplateRef<{ $el: HTMLElement }>('toggle');

// Ionic Vue drops disclosure ARIA from the host; keep it and the native button in sync.
async function syncAria(): Promise<void> {
  await nextTick();
  await customElements.whenDefined('ion-button');
  const host = toggle.value?.$el as (HTMLElement & { componentOnReady?: () => Promise<void> }) | undefined;
  await host?.componentOnReady?.();
  const native = host?.shadowRoot?.querySelector('button');
  for (const element of [host, native]) {
    element?.setAttribute('aria-expanded', String(expanded.value));
    element?.setAttribute('aria-controls', listId);
  }
}
onMounted(syncAria);
onUpdated(syncAria);
</script>

<template>
  <div class="collapsible-checklist">
    <ion-list
      :id="listId"
      lines="none"
      class="collapsible-checklist__list"
    >
      <ion-item
        v-for="(item, index) in visibleItems"
        :key="index"
        :data-testid="item.testid"
      >
        <HubIcon
          slot="start"
          name="ion:checkmark-outline"
          aria-hidden="true"
        />
        <ion-label class="ion-text-wrap">
          {{ item.text }}
        </ion-label>
      </ion-item>
    </ion-list>
    <div class="collapsible-checklist__disclosure">
      <ion-button
        v-if="items.length > collapsedCount"
        ref="toggle"
        class="collapsible-checklist__toggle"
        fill="clear"
        size="small"
        :aria-expanded="expanded ? 'true' : 'false'"
        :aria-controls="listId"
        :data-testid="toggleTestid"
        @click="expanded = !expanded"
      >
        <HubIcon
          slot="start"
          :name="expanded ? 'ion:chevron-up-outline' : 'ion:chevron-down-outline'"
          aria-hidden="true"
        />
        {{ expanded ? showFewerLabel : showAllLabel }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.collapsible-checklist {
  min-inline-size: 0;
}
.collapsible-checklist__list {
  min-inline-size: 0;
  margin: 0;
  padding: 0;
  background: transparent;
}
.collapsible-checklist__list ion-item {
  --background: transparent;
  --min-height: 0;
  --padding-start: 0;
  --inner-padding-end: 0;
  --padding-top: 3px;
  --padding-bottom: 3px;
  font-size: 0.9rem;
}
.collapsible-checklist__list ion-item ion-label {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.4;
  text-wrap: pretty;
  color: var(--ion-text-color);
}
.collapsible-checklist__list ion-icon {
  margin: 2px 8px 0 0;
  align-self: flex-start;
  font-size: 16px;
  color: var(--ep-success-text, var(--ion-color-success));
}
.collapsible-checklist__disclosure {
  min-block-size: 32px;
}
.collapsible-checklist__toggle {
  display: inline-flex;
  min-block-size: 32px;
  margin: 0;
  --border-radius: 8px;
  --color: var(--ep-primary-text, var(--ion-color-primary));
  --padding-start: 8px;
  --padding-end: 8px;
  --padding-top: 0;
  --padding-bottom: 0;
  font-size: 0.875rem;
  font-weight: 500;
}
.collapsible-checklist__toggle ion-icon {
  margin: 0 8px 0 0;
  font-size: 1.1em;
  color: currentcolor;
}
.collapsible-checklist__toggle::part(native):focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}
@media (max-width: 640px), (pointer: coarse) {
  .collapsible-checklist__disclosure,
  .collapsible-checklist__toggle {
    min-block-size: 44px;
  }
}
</style>
