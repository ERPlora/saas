<script setup lang="ts">
// Setting up the authenticator app (allauth's `mfa/totp/activate_form.html`): the QR and the key the page read, and
// the code typed back. When allauth asks for a recent login it is confirmed right here (password or code, as allauth
// lists), so the scanned secret stays valid. The page holds the state and makes the calls.
import type { FieldErrors, TotpSetup } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonInput, IonInputPasswordToggle } from '@ionic/vue';

import CodeField from './CodeField.vue';

defineProps<{
  setup: TotpSetup;
  /** The QR of allauth's `otpauth://` URL, as a data-URI image (CSP: `img-src data:`). */
  qrDataUrl: string;
  /** «Turn on» waiting for a recent login, and with what; `null` shows the setup. */
  confirmWith: 'password' | 'code' | null;
  busy: boolean;
  fields: FieldErrors;
}>();
defineEmits<{ turnOn: []; confirm: []; cancelConfirm: []; cancel: [] }>();

const code = defineModel<string>('code', { required: true });
const confirmPassword = defineModel<string>('confirmPassword', { required: true });
const confirmCode = defineModel<string>('confirmCode', { required: true });

const ICONS = {
  password: ionIconSrc('lucide:lock'),
  code: ionIconSrc('lucide:shield-check'),
};
</script>

<template>
  <div data-testid="activate-view">
    <div
      v-if="confirmWith"
      data-testid="activate-confirm"
    >
      <div class="auth-mark">
        <ion-icon
          class="auth-mark-icon"
          :icon="ICONS[confirmWith]"
          aria-hidden="true"
        />
      </div>
      <h2 class="auth-title">
        {{ $t('accounts.reauthenticate.title') }}
      </h2>
      <p
        class="auth-lead"
        data-testid="confirm-lead"
      >
        {{ confirmWith === 'password' ? $t('accounts.reauthenticate.passwordLead') : $t('accounts.reauthenticate.codeLead') }}
      </p>
      <form
        data-testid="confirm-form"
        novalidate
        @submit.prevent="$emit('confirm')"
      >
        <div
          v-if="confirmWith === 'password'"
          class="field"
        >
          <ion-input
            v-model="confirmPassword"
            data-testid="confirm-password"
            mode="md"
            type="password"
            :label="$t('accounts.reauthenticate.password')"
            label-placement="floating"
            fill="outline"
            placeholder="••••••••••"
            autocomplete="current-password"
            :required="true"
            :error-text="fields.password"
            :class="{ 'ion-invalid': !!fields.password, 'ion-touched': !!fields.password }"
          >
            <ion-input-password-toggle slot="end" />
          </ion-input>
        </div>
        <CodeField
          v-else
          v-model="confirmCode"
          :error="fields.code"
        />
        <ion-button
          type="submit"
          data-testid="confirm-submit"
          color="primary"
          size="large"
          expand="block"
          class="submit"
          :disabled="busy"
        >
          {{ $t('accounts.reauthenticate.confirm') }}
        </ion-button>
      </form>
      <ion-button
        data-testid="confirm-cancel"
        fill="clear"
        expand="block"
        class="after"
        :disabled="busy"
        @click="$emit('cancelConfirm')"
      >
        {{ $t('accounts.twoFactor.activate.cancel') }}
      </ion-button>
    </div>
    <template v-else>
      <h2 class="auth-title">
        {{ $t('accounts.twoFactor.activate.title') }}
      </h2>
      <p
        class="auth-lead"
        data-testid="activate-lead"
      >
        {{ $t('accounts.twoFactor.activate.lead') }}
      </p>
      <img
        class="qr"
        data-testid="totp-qr"
        :src="qrDataUrl"
        :alt="$t('accounts.twoFactor.activate.qrAlt')"
      >
      <p
        class="auth-lead secret-lead"
        data-testid="activate-cant-scan"
      >
        {{ $t('accounts.twoFactor.activate.cantScan') }}
      </p>
      <code class="auth-secret">{{ setup.secret }}</code>
      <form
        data-testid="activate-form"
        novalidate
        @submit.prevent="$emit('turnOn')"
      >
        <CodeField
          v-model="code"
          :error="fields.code"
        />
        <ion-button
          type="submit"
          data-testid="activate-submit"
          color="primary"
          size="large"
          expand="block"
          class="submit"
          :disabled="busy"
        >
          {{ $t('accounts.twoFactor.activate.turnOn') }}
        </ion-button>
      </form>
      <ion-button
        data-testid="activate-cancel"
        fill="clear"
        expand="block"
        class="after"
        :disabled="busy"
        @click="$emit('cancel')"
      >
        {{ $t('accounts.twoFactor.activate.cancel') }}
      </ion-button>
    </template>
  </div>
</template>

<style scoped src="./auth-card.css"></style>
<style scoped>
/* The template's inline `style="margin-top:1rem;"` on «Can't scan?». */
.secret-lead {
  margin-top: 1rem;
}
</style>
