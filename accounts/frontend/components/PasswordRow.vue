<script setup lang="ts">
// The «Password» row of Account → Security, «Sign-in» (mockups `account.html` «security», «Contraseña»): «Change
// password» opens its dialog (PasswordModal). An account that only signs in with Google has none, and the server
// never sets one with the session alone (`accounts/doors.py`): it gets one through «Forgot your password?», whose
// email link proves the mailbox (`/accounts/password/reset/`, a page of Django's: a full load).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { shallowRef } from 'vue';

import PasswordModal from './PasswordModal.vue';

defineProps<{
  hasPassword: boolean;
  email: string;
}>();

const PASSWORD_RESET = '/accounts/password/reset/';
const changing = shallowRef(false);
</script>

<template>
  <div
    class="card-row"
    data-testid="password-row"
  >
    <div class="card-row__text">
      <h3 class="card-row__title">
        {{ $t('accounts.account.password.row') }}
      </h3>
      <p class="card-text">
        {{ hasPassword ? $t('accounts.account.password.rowLead') : $t('accounts.account.password.none') }}
      </p>
    </div>
    <ion-button
      v-if="hasPassword"
      data-testid="password-row-change"
      fill="outline"
      @click="changing = true"
    >
      <HubIcon
        slot="start"
        name="lucide:key-round"
        aria-hidden="true"
      />
      {{ $t('accounts.account.password.submit') }}
    </ion-button>
    <ion-button
      v-else
      data-testid="password-row-create"
      fill="outline"
      :href="PASSWORD_RESET"
    >
      <HubIcon
        slot="start"
        name="lucide:key-round"
        aria-hidden="true"
      />
      {{ $t('accounts.account.password.create') }}
    </ion-button>
  </div>
  <PasswordModal
    v-if="hasPassword"
    v-model:open="changing"
    :email="email"
  />
</template>

<style scoped src="./account-card.css"></style>
