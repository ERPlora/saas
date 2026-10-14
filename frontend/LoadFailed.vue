<script setup lang="ts">
// The panel's one «could not load» state (audit 2026-10-14, R-04/R-08; `live-state.ts`): a danger notice that
// says what could not be loaded and offers «Retry» (the page reopens its live data). Pages pass their own
// heading; without one it speaks of the page. Never an empty state on a failure, never a spinner for ever.
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

withDefaults(
  defineProps<{
    /** What could not be loaded («We could not load your businesses.»). */
    heading?: string;
    /** Why, or what to do; the connection hint by default. */
    message?: string;
    /** `data-testid` of the notice and of its button. */
    testid?: string;
    retryTestid?: string;
  }>(),
  { heading: undefined, message: undefined, testid: 'load-failed', retryTestid: 'load-failed-retry' },
);

defineEmits<{ retry: [] }>();
</script>

<template>
  <InlineFeedback
    tone="danger"
    :heading="heading ?? $t('saas.load.heading')"
    :data-testid="testid"
  >
    {{ message ?? $t('saas.load.body') }}
    <template #actions>
      <ion-button
        :data-testid="retryTestid"
        size="small"
        fill="outline"
        class="load-failed__retry"
        @click="$emit('retry')"
      >
        <HubIcon
          slot="start"
          name="ion:refresh-outline"
          aria-hidden="true"
        />
        {{ $t('saas.load.retry') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>

<style scoped src="../hubs/frontend/components/buttons.css"></style>
<style scoped>
.load-failed__retry {
  min-height: 44px;
}
</style>
