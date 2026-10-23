<script setup lang="ts">
// `/password/reset` («Forgot your password?» of the sign-in), over allauth.headless: the pages of
// ERPlora/saas's `account/password_reset.html` (the address) and `password_reset_done.html` (check
// your email), same structure and texts, in the auth frame. allauth mails a link to
// `/password/reset/key/<key>` (PasswordResetKeyPage) and answers the same whether the address has an
// account or not, so the page says the same in both cases and never echoes the address. «Try again»
// goes back to the form with the address kept.
import { ApiError, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput } from '@ionic/vue';
import { computed, onMounted, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import { LAUNCHER } from '../paths';
import { createProtectedAllauthClient } from '../recaptcha';
import RecaptchaNotice from '../components/RecaptchaNotice.vue';

const NON_FIELD = '__all__';

const { t } = useI18n();
const router = useRouter();
const auth = createProtectedAllauthClient(useLiveClient().config);

const email = shallowRef('');
const sent = shallowRef(false);
const submitting = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

const subtitle = computed(() => t(sent.value ? 'accounts.passwordReset.checkSubtitle' : 'accounts.passwordReset.subtitle'));
const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

function retitle(): void {
  document.title = `${t(sent.value ? 'accounts.passwordReset.checkTitle' : 'accounts.passwordReset.title')} - ERPlora Cloud`;
}
onMounted(retitle);
watch(sent, retitle);

async function submit(): Promise<void> {
  submitting.value = true;
  fields.value = {};
  failure.value = '';
  try {
    await auth.requestPasswordReset(email.value);
    sent.value = true;
  } catch (error) {
    if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else if (error instanceof ApiError && error.status === 429) {
      failure.value = t('accounts.login.tooManyAttempts');
    } else {
      failure.value = t('accounts.passwordReset.failed');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AuthShell :subtitle="subtitle">
    <template v-if="sent">
      <p
        class="auth-lead"
        data-testid="password-reset-sent"
      >
        {{ $t('accounts.passwordReset.sent') }}
      </p>
      <ion-button
        data-testid="password-reset-back"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        @click="router.push(LAUNCHER)"
      >
        {{ $t('accounts.passwordReset.backToLogin') }}
      </ion-button>
    </template>

    <form
      v-else
      data-testid="password-reset-form"
      novalidate
      @submit.prevent="submit"
    >
      <div
        v-if="failure"
        class="non-field-error"
        role="alert"
      >
        {{ failure }}
      </div>

      <div class="field">
        <ion-input
          v-model="email"
          data-testid="password-reset-email"
          mode="md"
          type="email"
          :label="$t('accounts.login.email')"
          label-placement="floating"
          fill="outline"
          placeholder="you@example.com"
          autocomplete="email"
          required
          :error-text="fields.email"
          :class="invalid('email')"
        />
      </div>

      <ion-button
        type="submit"
        data-testid="password-reset-submit"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        :disabled="submitting"
      >
        {{ $t('accounts.passwordReset.send') }}
      </ion-button>
      <RecaptchaNotice />
    </form>

    <template #foot>
      <p
        v-if="sent"
        class="foot"
      >
        {{ $t('accounts.passwordReset.noEmail') }}
        <a
          href="#"
          data-testid="password-reset-again"
          @click.prevent="sent = false"
        >{{ $t('accounts.passwordReset.tryAgain') }}</a>
      </p>
      <p
        v-else
        class="foot"
      >
        {{ $t('accounts.passwordReset.remember') }}
        <router-link :to="LAUNCHER">
          {{ $t('accounts.passwordReset.signIn') }}
        </router-link>
      </p>
    </template>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
