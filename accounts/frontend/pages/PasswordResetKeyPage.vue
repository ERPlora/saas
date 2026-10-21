<script setup lang="ts">
// `/password/reset/key/:resetKey`: the page the reset link of the mail opens (allauth's
// `HEADLESS_FRONTEND_URLS`), over allauth.headless: ERPlora/saas's
// `account/password_reset_from_key.html`, same structure and texts. It checks the key first: an
// expired or used link says so («Request New Link», «Back to Login»), as the template's
// `token_fail` did. The new password goes in one field with its show toggle (allauth.headless takes
// one `password`), with the hint of Account's «Change password» under it (ACCOUNTS-G121: the rules in
// sight, and how strong it looks against the account's email, which the key's check returns); the
// server's validators (allauth's and Django's) decide, and their messages paint under the input. Done →
// the sign-in with «Your password has been changed» (`?notice=password_reset`), or on at once when the
// server signs the person in.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, createAllauthClient, type AuthState, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonInputPasswordToggle, IonSpinner } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import { passwordStrength } from '../password';
import { LAUNCHER } from '../paths';

const props = defineProps<{
  /** The key of the mailed link (the route's `:resetKey`). */
  resetKey: string;
}>();

const REQUEST = '/password/reset';
const TWO_FACTOR = '/2fa/authenticate';
/** allauth's flow of a login that waits for its second factor. */
const SECOND_FACTOR_FLOW = 'mfa_authenticate';
/** The sign-in's notice after a reset (SignInForm, in the launcher). */
const DONE_NOTICE = 'password_reset';
const NON_FIELD = '__all__';

const { t } = useI18n();
const router = useRouter();
const auth = createAllauthClient(useLiveClient().config);

/** `checking` the key, the form when it is `ready`, an `invalid` link, or the key could not be checked (`error`). */
const status = shallowRef<'checking' | 'ready' | 'invalid' | 'error'>('checking');
const password = shallowRef('');
/** The account of the link, from the key's check: the hint weighs the password against its email. */
const email = shallowRef('');
const strength = computed(() => passwordStrength(password.value, email.value));
const hint = computed(() => (strength.value === 'empty' ? t('accounts.account.password.hint') : t(`accounts.account.password.strength.${strength.value}`)));
const submitting = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

/** An error on the key: the link expired, was used, or never was one. */
const keyRefused = (error: unknown) => error instanceof ApiError && error.status === 400 && !!error.fields?.key;

async function check(): Promise<void> {
  status.value = 'checking';
  try {
    email.value = (await auth.passwordResetKeyInfo(props.resetKey)).email;
    status.value = 'ready';
  } catch (error) {
    status.value = keyRefused(error) ? 'invalid' : 'error';
  }
}

onMounted(() => {
  document.title = `${t('accounts.passwordReset.newTitle')} - ERPlora Cloud`;
  void check();
});

/** Signed in → the launcher; the second factor next → its page; else the sign-in, with the notice. */
function follow(state: AuthState): void {
  if (state.authenticated) location.assign(LAUNCHER);
  else if (state.pendingFlow === SECOND_FACTOR_FLOW) void router.replace(TWO_FACTOR);
  else void router.replace({ path: LAUNCHER, query: { notice: DONE_NOTICE } });
}

async function submit(): Promise<void> {
  submitting.value = true;
  fields.value = {};
  failure.value = '';
  try {
    follow(await auth.resetPassword(props.resetKey, password.value));
  } catch (error) {
    if (keyRefused(error)) {
      status.value = 'invalid';
    } else if (error instanceof ApiError && error.fields) {
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
  <AuthShell :subtitle="$t('accounts.passwordReset.newSubtitle')">
    <div
      v-if="status === 'checking'"
      class="status"
      data-testid="password-reset-key-checking"
    >
      <ion-spinner name="crescent" />
      <p class="auth-lead">
        {{ $t('accounts.passwordReset.checking') }}
      </p>
    </div>

    <template v-else-if="status === 'error'">
      <div
        class="non-field-error"
        role="alert"
      >
        {{ $t('accounts.passwordReset.failed') }}
      </div>
      <ion-button
        data-testid="password-reset-key-retry"
        fill="outline"
        expand="block"
        @click="check"
      >
        {{ $t('accounts.passwordReset.tryAgain') }}
      </ion-button>
    </template>

    <template v-else-if="status === 'invalid'">
      <InlineFeedback
        tone="danger"
        data-testid="password-reset-key-invalid"
      >
        {{ $t('accounts.passwordReset.invalidLink') }}
      </InlineFeedback>
      <ion-button
        data-testid="password-reset-key-request"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        @click="router.push(REQUEST)"
      >
        {{ $t('accounts.passwordReset.requestNewLink') }}
      </ion-button>
      <ion-button
        data-testid="password-reset-key-back"
        fill="clear"
        expand="block"
        class="after"
        @click="router.push(LAUNCHER)"
      >
        {{ $t('accounts.passwordReset.backToLogin') }}
      </ion-button>
    </template>

    <form
      v-else
      data-testid="password-reset-key-form"
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
          v-model="password"
          data-testid="password-reset-key-password"
          mode="md"
          type="password"
          :label="$t('accounts.passwordReset.newPassword')"
          label-placement="floating"
          fill="outline"
          placeholder="••••••••••"
          autocomplete="new-password"
          required
          :helper-text="hint"
          :error-text="fields.password"
          :class="[invalid('password'), `strength-${strength}`]"
        >
          <ion-input-password-toggle slot="end" />
        </ion-input>
      </div>

      <ion-button
        type="submit"
        data-testid="password-reset-key-submit"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        :disabled="submitting"
      >
        {{ $t('accounts.passwordReset.change') }}
      </ion-button>
    </form>

    <template
      v-if="status === 'ready'"
      #foot
    >
      <p class="foot">
        {{ $t('accounts.passwordReset.remember') }}
        <router-link :to="LAUNCHER">
          {{ $t('accounts.passwordReset.signIn') }}
        </router-link>
      </p>
    </template>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
