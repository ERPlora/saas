<script setup lang="ts">
// «On your devices» (mockups `business.html` Summary; it replaces the old QR page, README §3): the
// business's address to open in the browser of the till, the tablet or the phone, with «Copy»; on
// the web, the apps for Windows and Android through the public download doors
// (`/app/download/<platform>/`, public/appdist.py: the store or the installer). Inside the apps the
// buttons go (an app does not download itself) and the sentence speaks of the other devices.
import { HubIcon, WebOnly } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent } from '@ionic/vue';

import CopyField from './CopyField.vue';

defineProps<{
  /** The business's address (`<slug>.erplora.com`). */
  host: string;
}>();
</script>

<template>
  <ion-card data-testid="device-access-card">
    <ion-card-content class="ion-padding">
      <div class="page-eyebrow">
        {{ $t('hubs.business.devices.eyebrow') }}
      </div>
      <h2 class="card-title">
        {{ $t('hubs.business.devices.title') }}
      </h2>
      <WebOnly>
        <p class="card-text">
          {{ $t('hubs.business.devices.body') }}
        </p>
        <template #app>
          <p class="card-text">
            {{ $t('hubs.business.devices.bodyApp') }}
          </p>
        </template>
      </WebOnly>
      <CopyField
        class="ion-margin-top"
        :value="host"
        :label="$t('hubs.business.devices.address')"
      />
      <WebOnly>
        <div class="card-actions">
          <ion-button
            data-testid="device-windows"
            fill="outline"
            href="/app/download/windows/"
          >
            <HubIcon
              slot="start"
              name="ion:download-outline"
            />
            {{ $t('hubs.business.devices.windows') }}
          </ion-button>
          <ion-button
            data-testid="device-android"
            fill="outline"
            href="/app/download/android/"
          >
            <HubIcon
              slot="start"
              name="lucide:smartphone"
            />
            {{ $t('hubs.business.devices.android') }}
          </ion-button>
        </div>
      </WebOnly>
    </ion-card-content>
  </ion-card>
</template>

<style scoped src="./buttons.css"></style>
<style scoped src="./panel-card.css"></style>
