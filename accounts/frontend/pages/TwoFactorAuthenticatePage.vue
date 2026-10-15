<script setup lang="ts">
// The second step of a sign-in with two-factor authentication (`/2fa/authenticate`), over
// allauth.headless: the page of `templates/mfa/authenticate.html`, same structure and texts. The
// login waits in the session (`mfa_authenticate` pending) until a code from the authenticator app
// or a recovery code is right; then the visitor leaves the SPA for `next` or the launcher, with a
// full page load that brings the new session, as the sign-in does. No session yet, so no «Back to
// settings» foot. «Back to sign in» ends the waiting login first: allauth would resume the stage on
// the sign-in page otherwise (the template posted the logout for the same reason). With no login
// waiting, allauth answers the code with a 401 and no pending flow (never 409): the session then
// says whether another tab finished the sign-in (→ on) or the login expired (→ the sign-in).
import { ApiError, createAllauthClient, type AuthState, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import CodeField from '../components/CodeField.vue';
import { localNext } from '../next';
import { LAUNCHER } from '../paths';

/** allauth's flow of a login that waits for its second factor. */
const PENDING_FLOW = 'mfa_authenticate';
const NON_FIELD = '__all__';
const SHIELD_ICON = ionIconSrc('lucide:shield-check');

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = createAllauthClient(useLiveClient().config);

const code = shallowRef('');
const submitting = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

const next = computed(() => localNext(route.query.next));
const signIn = computed(() => ({ path: LAUNCHER, query: next.value ? { next: next.value } : {} }));

function leave(): void {
  location.assign(next.value ?? LAUNCHER);
}

/** Signed in → on to `next`; no login waiting for its code (none, or expired) → the sign-in. */
function follow(state: AuthState): boolean {
  if (state.authenticated) leave();
  else if (state.pendingFlow !== PENDING_FLOW) void router.replace(signIn.value);
  else return false;
  return true;
}

onMounted(async () => {
  document.title = `${t('accounts.twoFactor.title')} - ERPlora Cloud`;
  try {
    follow(await auth.getSession());
  } catch {
    failure.value = t('accounts.login.failed');
  }
});

async function submit(): Promise<void> {
  submitting.value = true;
  fields.value = {};
  failure.value = '';
  try {
    let state = await auth.mfaAuthenticate(code.value);
    if (!state.authenticated && state.pendingFlow !== PENDING_FLOW) state = await auth.getSession();
    if (!follow(state)) failure.value = t('accounts.login.failed');
  } catch (error) {
    if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else {
      failure.value = t('accounts.login.failed');
    }
  } finally {
    submitting.value = false;
  }
}

async function backToSignIn(): Promise<void> {
  failure.value = '';
  submitting.value = true;
  try {
    await auth.logout();
    await router.push(signIn.value);
  } catch {
    failure.value = t('accounts.login.failed');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AuthShell :subtitle="$t('accounts.twoFactor.title')">
    <div class="auth-mark">
      <ion-icon
        class="auth-mark-icon"
        :icon="SHIELD_ICON"
        aria-hidden="true"
      />
    </div>
    <h2 class="auth-title">
      {{ $t('accounts.twoFactor.title') }}
    </h2>
    <p class="auth-lead">
      {{ $t('accounts.twoFactor.lead') }}
    </p>

    <div
      v-if="failure"
      class="non-field-error"
      role="alert"
    >
      {{ failure }}
    </div>

    <form
      data-testid="mfa-form"
      novalidate
      @submit.prevent="submit"
    >
      <CodeField
        v-model="code"
        :error="fields.code"
      />
      <ion-button
        type="submit"
        data-testid="mfa-submit"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        :disabled="submitting"
      >
        {{ $t('accounts.twoFactor.verify') }}
      </ion-button>
    </form>

    <ion-button
      data-testid="mfa-back"
      fill="clear"
      expand="block"
      class="after"
      :disabled="submitting"
      @click="backToSignIn"
    >
      {{ $t('accounts.twoFactor.backToSignIn') }}
    </ion-button>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
