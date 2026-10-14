<script setup lang="ts">
// «Change photo» / «Remove photo» of Account → Profile (mockups `account.html`, next to the avatar): the device's
// picker for a JPEG, PNG or WebP; the image is made small in the browser (`../photo.ts`: 512 px, 150 KB, still)
// and sent as a data URL (`accounts.photo.upload`). Removing it goes back to the initials. A file that cannot be
// the photo, or the server's refusal, is said in a toast.
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { ApiError, useCommand } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, useTemplateRef } from 'vue';
import { useI18n } from 'vue-i18n';

import type { ProfileOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import { PHOTO_TYPES, PhotoError, preparePhoto } from '../photo';

defineProps<{
  profile: Pick<ProfileOut, 'photo'>;
}>();

const { t } = useI18n();
const { text } = useErrorText();
const upload = useCommand('accounts.photo.upload');
const remove = useCommand('accounts.photo.remove');
const input = useTemplateRef<HTMLInputElement>('input');
const busy = computed(() => upload.pending.value || remove.pending.value);
const ACCEPT = PHOTO_TYPES.join(',');

/** What the person reads for a failure: ours for a file the browser refused, else the server's. */
function failure(error: unknown): string {
  if (error instanceof PhotoError) return t(`accounts.account.photo.errors.${error.reason}`);
  if (error instanceof ApiError) return error.fields?.image ?? text(error);
  return t('accounts.account.errors.unexpected');
}

async function onPicked(event: Event): Promise<void> {
  const field = event.target as HTMLInputElement;
  const file = field.files?.[0];
  if (!file) return;
  try {
    const image = await preparePhoto(file);
    await upload.run({ image });
    void toastSuccess(t('accounts.account.photo.updated'));
  } catch (error) {
    void toastError(failure(error));
  } finally {
    // The same file picked again is a new pick.
    field.value = '';
  }
}

async function clear(): Promise<void> {
  try {
    await remove.run({});
    void toastSuccess(t('accounts.account.photo.removed'));
  } catch (error) {
    void toastError(failure(error));
  }
}
</script>

<template>
  <div class="photo-picker">
    <input
      ref="input"
      data-testid="photo-input"
      class="photo-input"
      type="file"
      :accept="ACCEPT"
      tabindex="-1"
      aria-hidden="true"
      @change="onPicked"
    >
    <ion-button
      data-testid="photo-change"
      fill="outline"
      size="small"
      :disabled="busy"
      @click="input?.click()"
    >
      <ion-spinner
        v-if="upload.pending.value"
        slot="start"
        name="crescent"
        aria-hidden="true"
      />
      <HubIcon
        v-else
        slot="start"
        name="lucide:camera"
        aria-hidden="true"
      />
      {{ $t('accounts.account.photo.change') }}
    </ion-button>
    <ion-button
      v-if="profile.photo"
      data-testid="photo-remove"
      fill="clear"
      size="small"
      color="danger"
      :disabled="busy"
      @click="clear"
    >
      <HubIcon
        slot="start"
        name="ion:trash-outline"
        aria-hidden="true"
      />
      {{ $t('accounts.account.photo.remove') }}
    </ion-button>
  </div>
</template>

<style scoped>
.photo-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
}
.photo-picker ion-button {
  margin: 0;
  text-transform: none;
}
.photo-picker ion-button > ion-icon[slot='start'],
.photo-picker ion-button > ion-spinner[slot='start'] {
  margin-inline-end: 0.45em;
}
.photo-input {
  display: none;
}
</style>
