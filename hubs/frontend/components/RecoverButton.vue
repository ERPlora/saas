<script setup lang="ts">
// «Recover business», the arrow back, wherever a deleted business is listed: as wide as its card it is the card's
// main action and says it in words; small in a list it is its icon, named with its business. Only what the server
// allows (`can.restore`: its owner, within its 90 days); it runs `hubs.business.restore` and says the result, or the
// server's sentence when it is refused (the Free quota taken meanwhile…).
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessRowOut } from '../../../frontend/sdk-types/hubs';
import { useErrorText } from '../error-text';

const props = withDefaults(
  defineProps<{
    business: Pick<BusinessRowOut, 'id' | 'name'> & { can: Pick<BusinessRowOut['can'], 'restore'> };
    /** In a list: its accessible name says its business. */
    named?: boolean;
    size?: 'small' | 'default' | 'large';
    /** `block` in a card that stacks its actions. */
    expand?: 'block';
  }>(),
  { named: false, size: 'default', expand: undefined },
);

const { t } = useI18n();
const { text } = useErrorText();
const restore = useCommand('hubs.business.restore');
const name = computed(() => (props.named ? t('hubs.list.actions.restoreName', { name: props.business.name }) : t('hubs.danger.restore')));

async function recover(): Promise<void> {
  try {
    const recovered = await restore.run({ id: props.business.id });
    toastSuccess(t('hubs.list.restored', { name: recovered.name }));
  } catch {
    toastError(text(restore.error.value));
  }
}
</script>

<template>
  <ion-button
    v-if="business.can.restore"
    :class="{ 'icon-action': !expand }"
    data-testid="recover-business"
    :size="size === 'default' ? undefined : size"
    :expand="expand"
    :aria-label="expand && !named ? undefined : name"
    :title="expand ? undefined : name"
    :disabled="restore.pending.value"
    @click="recover"
  >
    <template v-if="expand">
      <ion-spinner
        v-if="restore.pending.value"
        slot="start"
        name="crescent"
        aria-hidden="true"
      />
      <HubIcon
        v-else
        slot="start"
        name="ion:arrow-undo-outline"
        aria-hidden="true"
      />
      {{ $t('hubs.danger.restore') }}
    </template>
    <template v-else>
      <ion-spinner
        v-if="restore.pending.value"
        slot="icon-only"
        name="crescent"
        aria-hidden="true"
      />
      <HubIcon
        v-else
        slot="icon-only"
        name="ion:arrow-undo-outline"
        aria-hidden="true"
      />
    </template>
  </ion-button>
</template>

<style scoped src="./buttons.css"></style>
