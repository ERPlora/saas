<script setup lang="ts">
// «Recover business» wherever a deleted business is listed (audit 2 R-07: the launch card offered only «Go to
// the panel»). Only what the server allows (`can.restore`: its owner, within its 90 days); it runs
// `hubs.business.restore` and says the result, or the server's sentence when it is refused (the Free quota
// taken meanwhile…). In a list the button is named with its business.
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

import type { BusinessRowOut } from '../../../frontend/sdk-types';
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

async function recover(): Promise<void> {
  try {
    const recovered = await restore.run({ id: props.business.id });
    void toastSuccess(t('hubs.list.restored', { name: recovered.name }));
  } catch {
    void toastError(text(restore.error.value));
  }
}
</script>

<template>
  <ion-button
    v-if="business.can.restore"
    data-testid="recover-business"
    :size="size === 'default' ? undefined : size"
    :expand="expand"
    :aria-label="named ? $t('hubs.list.actions.restoreName', { name: business.name }) : undefined"
    :disabled="restore.pending.value"
    @click="recover"
  >
    <ion-spinner
      v-if="restore.pending.value"
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
    {{ $t('hubs.danger.restore') }}
  </ion-button>
</template>

<style scoped src="./buttons.css"></style>
