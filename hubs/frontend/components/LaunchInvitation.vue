<script setup lang="ts">
// Invited, without a business of one's own, the entry's card is the invitation: accept and enter, decline, or create
// one's own. The page runs the acceptance and holds the decline dialog, so each button hands its answer back to it.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';

import type { InvitationOut } from '../../../frontend/sdk-types/hubs';

defineProps<{ invitation: InvitationOut; accepting: string | null }>();
const emit = defineEmits<{ accept: [invitation: InvitationOut]; decline: [invitation: InvitationOut]; createOwn: [] }>();
</script>

<template>
  <ion-button
    data-testid="launch-accept"
    expand="block"
    size="large"
    class="launch-main"
    :disabled="!!accepting"
    @click="emit('accept', invitation)"
  >
    <ion-spinner
      v-if="accepting === invitation.id"
      slot="start"
      name="crescent"
      aria-hidden="true"
    />
    <HubIcon
      v-else
      slot="start"
      name="ion:log-in-outline"
      aria-hidden="true"
    />
    {{ $t('hubs.invitation.accept') }}
  </ion-button>
  <ion-button
    data-testid="launch-decline"
    expand="block"
    fill="outline"
    class="btn-neutral"
    :disabled="!!accepting"
    @click="emit('decline', invitation)"
  >
    <HubIcon
      slot="start"
      name="ion:close-outline"
      aria-hidden="true"
    />
    {{ $t('hubs.invitation.decline') }}
  </ion-button>
  <ion-button
    data-testid="launch-create-own"
    class="link-button"
    expand="block"
    fill="clear"
    @click="emit('createOwn')"
  >
    <HubIcon
      slot="start"
      name="ion:add-outline"
      aria-hidden="true"
    />
    {{ $t('hubs.launch.invited.createOwn') }}
  </ion-button>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
.launch-main {
  margin-top: 16px;
}
ion-button[expand='block'] + ion-button[expand='block'] {
  margin-top: 10px;
}
.btn-neutral {
  --color: var(--ion-text-color);
  --border-color: color-mix(in oklab, var(--ion-text-color) 35%, transparent);
}
</style>
