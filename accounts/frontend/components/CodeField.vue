<script setup lang="ts">
// The code input of every second-factor screen (the sign-in's 2FA step, the authenticator setup and
// the reauthentication), ported from `account/_auth_code_field.html`: a 6-digit code from the app
// or a recovery code (hence 16 characters, not 6), the numeric keypad and the browser's
// one-time-code autofill. Its error, when there is one, paints under it.
import { IonInput } from '@ionic/vue';

defineProps<{
  /** allauth's message for the `code` field (already translated by the server). */
  error?: string;
}>();

const code = defineModel<string>({ required: true });
</script>

<template>
  <div class="field">
    <ion-input
      v-model="code"
      data-testid="code"
      mode="md"
      type="text"
      :label="$t('accounts.twoFactor.code')"
      label-placement="floating"
      fill="outline"
      placeholder="000000"
      inputmode="numeric"
      autocomplete="one-time-code"
      :maxlength="16"
      :required="true"
      class="otp-input"
      :error-text="error"
      :class="{ 'ion-invalid': !!error, 'ion-touched': !!error }"
    />
  </div>
</template>

<style scoped>
/* Ported from `templates/account/_auth_styles.html` (second factor). */
.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.otp-input {
  letter-spacing: 0.12em;
}
</style>
