<script setup lang="ts">
// The «Password» row of Account → Security, «Sign-in» (mockups `account.html` «security», «Contraseña»): «Change
// password» opens its dialog (PasswordModal). An account that only signs in with Google has none, and the server
// never sets one with the session alone (`accounts/doors.py`): it gets one through «Forgot your password?», whose
// email link proves the mailbox (the SPA's `/password/reset`).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { shallowRef } from 'vue';

import PasswordModal from './PasswordModal.vue';

defineProps<{
  hasPassword: boolean;
  email: string;
}>();

const PASSWORD_RESET = '/password/reset';
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
      class="icon-action"
      data-testid="password-row-change"
      fill="outline"
      :aria-label="$t('accounts.account.password.submit')"
      :title="$t('accounts.account.password.submit')"
      @click="changing = true"
    >
      <HubIcon
        slot="icon-only"
        name="lucide:pencil"
        aria-hidden="true"
      />
    </ion-button>
    <ion-button
      v-else
      class="icon-action"
      data-testid="password-row-create"
      fill="outline"
      :router-link="PASSWORD_RESET"
      :aria-label="$t('accounts.account.password.create')"
      :title="$t('accounts.account.password.create')"
    >
      <HubIcon
        slot="icon-only"
        name="ion:add-outline"
        aria-hidden="true"
      />
    </ion-button>
  </div>
  <PasswordModal
    v-if="hasPassword"
    v-model:open="changing"
    :email="email"
  />
</template>

<style scoped src="./account-card.css"></style>
