<script setup lang="ts">
// The preparation of a new business (mockups `launch.html` «first-preparing», `businesses.html`
// «creating»; the old SaaS's `deploy-steps` of `cloud.css`): a running bar (we do not know how far it
// is, so it does not pretend a percentage) and three steps — created, being set up, and what happens
// next. The list is a live region: a screen reader hears the step change.
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonProgressBar, IonSpinner } from '@ionic/vue';
import { onMounted, shallowRef } from 'vue';

import type { HubMaintenanceOut } from '../../../frontend/sdk-types';

const props = defineProps<{
  /** The business id, when its server status can be checked. */
  id?: string;
  /** The business's name. */
  name: string;
  /** The business type picked at the sign-up, if any (the step names it; a business is born with every app off, PLAN §33). */
  typeName?: string | null;
  /** The real platform-wide pause reported by the Hub. */
  maintenance?: HubMaintenanceOut | null;
  /** The last step: the launcher opens it by itself; the dialog offers to open it. */
  last: 'opensAlone' | 'ready';
}>();

const check = useCommand('hubs.business.check');
const checkFailed = shallowRef(false);

async function checkStatus(): Promise<void> {
  if (!props.id || check.pending.value) return;
  checkFailed.value = false;
  try {
    await check.run({ id: props.id });
  } catch {
    checkFailed.value = true;
  }
}
onMounted(() => {
  void checkStatus();
});
</script>

<template>
  <div class="progress-block">
    <ion-progress-bar
      type="indeterminate"
      :aria-label="$t('hubs.preparing.progress')"
    />
    <ol
      class="deploy-steps"
      role="status"
      aria-live="polite"
      :aria-label="$t('hubs.preparing.status', { name })"
    >
      <li class="done ion-padding-horizontal">
        <span class="step-icon"><HubIcon
          name="ion:checkmark-circle-outline"
          aria-hidden="true"
        /></span>
        <span>{{ $t('hubs.preparing.created') }}</span>
      </li>
      <li
        class="current ion-padding-horizontal"
        aria-current="step"
      >
        <span class="step-icon"><ion-spinner
          v-if="!maintenance?.frozen"
          name="crescent"
          aria-hidden="true"
        /><HubIcon
          v-else
          name="ion:time-outline"
          aria-hidden="true"
        /></span>
        <span>{{ typeName ? $t('hubs.preparing.setupType', { type: typeName }) : $t('hubs.preparing.setup') }}</span>
      </li>
      <li class="pending ion-padding-horizontal">
        <span class="step-icon"><HubIcon
          name="ion:log-in-outline"
          aria-hidden="true"
        /></span>
        <span>{{ $t(`hubs.preparing.${last}`) }}</span>
      </li>
    </ol>
    <InlineFeedback
      v-if="maintenance?.frozen"
      tone="warning"
      data-testid="preparing-maintenance"
    >
      {{ $t('hubs.preparing.maintenance') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="checkFailed"
      tone="danger"
      data-testid="preparing-check-error"
    >
      {{ $t('hubs.preparing.checkError') }}
    </InlineFeedback>
    <ion-button
      v-if="id"
      fill="outline"
      data-testid="preparing-check"
      :disabled="check.pending.value"
      @click="checkStatus"
    >
      <ion-spinner
        v-if="check.pending.value"
        slot="start"
        name="crescent"
        aria-hidden="true"
      />
      <HubIcon
        v-else
        slot="start"
        name="ion:refresh-outline"
        aria-hidden="true"
      />
      {{ $t('hubs.preparing.checkNow') }}
    </ion-button>
  </div>
</template>

<style scoped>
/* `cloud.css` (deploy-steps) and `mock.css` (progress-block) of the mockups, with our tokens. */
.progress-block {
  display: grid;
  gap: 14px;
}
.progress-block ion-progress-bar {
  border-radius: 999px;
  height: 6px;
}
.deploy-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}
.deploy-steps li {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  border-radius: 8px;
  font-size: 0.95rem;
}
.step-icon {
  display: inline-flex;
  width: 20px;
  justify-content: center;
  font-size: 16px;
}
.step-icon ion-spinner {
  width: 16px;
  height: 16px;
}
.deploy-steps li.done,
.deploy-steps li.current {
  color: var(--ion-text-color);
}
.deploy-steps li.done .step-icon {
  color: var(--ion-color-success);
}
.deploy-steps li.current {
  font-weight: 600;
  background: color-mix(in srgb, var(--ion-color-primary) 10%, transparent);
}
.deploy-steps li.current .step-icon {
  color: var(--ion-color-primary);
}
.deploy-steps li.pending {
  color: color-mix(in oklab, var(--ion-text-color) 62%, transparent);
}
</style>
