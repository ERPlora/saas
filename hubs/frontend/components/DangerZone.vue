<script setup lang="ts">
// The Danger zone of a business's Settings (mockups `business.html` «settings», PLAN-SAAS §3.4, round
// 17 §2.11): «Delete business» with its 90-day notice, only for the owner (DeleteDialog asks for the
// name); anybody else reads that only the owner can. Deleted and within its 90 days, the owner gets
// «Recover business» (`hubs.business.restore`; it comes back on Free). Both follow the server's `can`
// (`delete`, `restore`): a deleted business takes no `delete`.
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSpinner } from '@ionic/vue';
import { shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessDetailOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import DeleteDialog from './DeleteDialog.vue';

const props = defineProps<{
  business: Pick<BusinessDetailOut, 'id' | 'name' | 'status' | 'purge_after'> & {
    can: Pick<BusinessDetailOut['can'], 'delete' | 'restore'>;
  };
}>();

const { t } = useI18n();
const { text } = useErrorText();
const restore = useCommand('hubs.business.restore');
const deleting = shallowRef(false);

async function recover(): Promise<void> {
  try {
    const business = await restore.run({ id: props.business.id });
    void toastSuccess(t('hubs.list.restored', { name: business.name }));
  } catch {
    void toastError(text(restore.error.value));
  }
}
</script>

<template>
  <ion-card
    class="danger-zone"
    data-testid="danger-zone"
  >
    <ion-card-content class="ion-padding">
      <h2 class="card-title">
        {{ $t('hubs.danger.title') }}
      </h2>
      <div class="danger-row">
        <div>
          <h3>{{ business.status === 'deleting' ? $t('hubs.danger.restore') : $t('hubs.danger.deleteTitle') }}</h3>
          <p v-if="business.status !== 'deleting'">
            {{ business.can.delete ? $t('hubs.danger.deleteBody') : $t('hubs.danger.ownerOnly') }}
          </p>
        </div>
        <ion-button
          v-if="business.can.restore"
          data-testid="danger-restore"
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
        <ion-button
          v-else-if="business.can.delete"
          data-testid="danger-delete"
          color="danger"
          @click="deleting = true"
        >
          <HubIcon
            slot="start"
            name="ion:trash-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.danger.deleteAction') }}
        </ion-button>
      </div>
    </ion-card-content>
    <DeleteDialog
      v-model:open="deleting"
      :business="business"
    />
  </ion-card>
</template>

<style scoped src="./buttons.css"></style>
<style scoped src="./panel-card.css"></style>
<style scoped>
.danger-zone {
  border: 1px solid color-mix(in srgb, var(--ion-color-danger) 45%, transparent);
  box-shadow: none;
}
.danger-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
}
.danger-row > div {
  flex: 1 1 280px;
  min-width: 0;
}
.danger-row h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.danger-row p {
  margin: 3px 0 0;
  font-size: 0.85rem;
  line-height: 1.45;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
</style>
