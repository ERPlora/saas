<script setup lang="ts">
// «Your data» of Account → Profile (ACCOUNTS-F26; GDPR art. 20), above the danger card as GitHub's «Export account
// data» sits above its «Delete account»: «Download my data» reads `accounts.data.export` (the account, its
// businesses and ERPlora's invoices it sees) and saves it as a JSON file built here, named with the day. While it runs
// the button is off; a failure is said in a toast and the button comes back.
import { HubIcon, toastError } from '@erplora/ui/shell';
import { ApiError, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent } from '@ionic/vue';
import { shallowRef } from 'vue';

import { useErrorText } from '../error-text';

/** How long the saved file's object URL lives: the browser has started the download well before. */
const DOWNLOAD_URL_TTL_MS = 10_000;

const client = useLiveClient();
const { text } = useErrorText();
const running = shallowRef(false);

/** Saves `data` as `erplora-data-<day>.json` through a same-origin link. */
function save(data: unknown): void {
  const day = new Date().toISOString().slice(0, 10);
  const url = URL.createObjectURL(new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `erplora-data-${day}.json`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_TTL_MS);
}

async function download(): Promise<void> {
  if (running.value) return;
  running.value = true;
  try {
    save(await client.api.call('accounts.data.export'));
  } catch (error) {
    const failure = error instanceof ApiError ? error : new ApiError(0, 'client_error', String(error));
    void toastError(text(failure));
  } finally {
    running.value = false;
  }
}
</script>

<template>
  <ion-card data-testid="profile-export-card">
    <ion-card-content class="ion-padding">
      <div class="card-row">
        <div class="card-row__text">
          <h2 class="card-row__title">
            {{ $t('accounts.account.export.title') }}
          </h2>
          <p class="card-text">
            {{ $t('accounts.account.export.lead') }}
          </p>
        </div>
        <ion-button
          data-testid="profile-export"
          fill="outline"
          :disabled="running"
          @click="download"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
            aria-hidden="true"
          />
          {{ $t('accounts.account.export.download') }}
        </ion-button>
      </div>
    </ion-card-content>
  </ion-card>
</template>

<style scoped src="./account-card.css"></style>
<style scoped>
.card-row {
  padding: 0;
}
</style>
