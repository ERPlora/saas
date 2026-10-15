<script setup lang="ts">
// The panel's one «could not load» state (audit 2026-10-14, R-04/R-08; `live-state.ts`): a danger notice that
// says what could not be loaded and offers «Retry» (the page reopens its live data). Pages pass their own
// heading; without one it speaks of the page. Never an empty state on a failure, never a spinner for ever.
// A refusal for the person's role (403 or the live `permission_denied`) is not a connection problem: it says so
// and offers no «Retry», which would only be refused again (audit 2 R-19).
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    /** What could not be loaded («We could not load your businesses.»). */
    heading?: string;
    /** Why, or what to do; the connection hint by default. */
    message?: string;
    /** The failure (`useLiveState().error`): a refusal for the role is said as such. */
    error?: { code: string; status: number } | null;
    /** What may not be seen, when the role is refused («You do not have permission to manage this business»). */
    forbiddenHeading?: string;
    /** `data-testid` of the notice and of its button. */
    testid?: string;
    retryTestid?: string;
  }>(),
  {
    heading: undefined,
    message: undefined,
    error: null,
    forbiddenHeading: undefined,
    testid: 'load-failed',
    retryTestid: 'load-failed-retry',
  },
);

defineEmits<{ retry: [] }>();

const forbidden = computed(() => props.error?.code === 'permission_denied' || props.error?.status === 403);
</script>

<template>
  <InlineFeedback
    v-if="forbidden"
    tone="danger"
    icon="ion:lock-closed-outline"
    :heading="forbiddenHeading ?? $t('saas.load.forbiddenHeading')"
    :data-testid="testid"
  >
    {{ $t('saas.load.forbiddenBody') }}
  </InlineFeedback>
  <InlineFeedback
    v-else
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
  /* On the notice's pink the primary is 3.94:1 (audit 2 R-10): the accessible primary text reads ≥ 4.5:1. */
  --color: var(--ep-primary-text, var(--ion-color-primary));
  --border-color: var(--ep-primary-text, var(--ion-color-primary));
}
</style>
