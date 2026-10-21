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
//
// «Trust this browser for 14 days» (ACCOUNTS-F05, `MFA_TRUST_ENABLED`): opt-in, under the code, and answered with the
// same «Verify», as Google's and Microsoft's «Don't ask again on this device». A right code leaves the login waiting
// for that answer (allauth's `mfa_trust` stage); the page gives it at once (`auth.mfaTrust`) and follows the session it
// answers. Should the answer get lost (or the page be reloaded meanwhile), the page asks only the question, without
// the code. With no login waiting for it any more, allauth answers it as the code: a 401 without a pending flow (never a
// 409), and the session says whether another tab finished the sign-in (→ on) or the login expired (→ the sign-in).
import { ApiError, createAllauthClient, type AuthState, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonCheckbox, IonIcon } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import CodeField from '../components/CodeField.vue';
import { localNext } from '../next';
import { LAUNCHER } from '../paths';

/** allauth's flows of a login that waits for its second factor, then for «Trust this browser». */
const PENDING_FLOW = 'mfa_authenticate';
const TRUST_FLOW = 'mfa_trust';
const NON_FIELD = '__all__';
const SHIELD_ICON = ionIconSrc('lucide:shield-check');

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = createAllauthClient(useLiveClient().config);

/** What the login waits for: the code, or the answer to «Trust this browser». */
const step = shallowRef<'code' | 'trust'>('code');
const code = shallowRef('');
const trust = shallowRef(false);
const submitting = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

const next = computed(() => localNext(route.query.next));
const signIn = computed(() => ({ path: LAUNCHER, query: next.value ? { next: next.value } : {} }));

function leave(): void {
  location.assign(next.value ?? LAUNCHER);
}

/**
 * Signed in → on to `next`; a login waiting for its code or for the trust question → that step, here; no login
 * waiting (none, or expired) → the sign-in.
 */
function follow(state: AuthState): boolean {
  if (state.authenticated) leave();
  else if (state.pendingFlow === PENDING_FLOW || state.pendingFlow === TRUST_FLOW) {
    step.value = state.pendingFlow === TRUST_FLOW ? 'trust' : 'code';
    return false;
  } else void router.replace(signIn.value);
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
    let state = step.value === 'code' ? await auth.mfaAuthenticate(code.value) : undefined;
    if (state === undefined || (!state.authenticated && state.pendingFlow === TRUST_FLOW)) {
      step.value = 'trust';
      state = await auth.mfaTrust(trust.value);
      if (!state.authenticated && state.pendingFlow !== TRUST_FLOW) state = await auth.getSession();
    } else if (!state.authenticated && state.pendingFlow !== PENDING_FLOW) state = await auth.getSession();
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
    <p
      class="auth-lead"
      data-testid="mfa-lead"
    >
      {{ step === 'trust' ? $t('accounts.twoFactor.trustLead') : $t('accounts.twoFactor.lead') }}
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
        v-if="step === 'code'"
        v-model="code"
        :error="fields.code"
      />
      <div class="trust">
        <ion-checkbox
          data-testid="mfa-trust"
          label-placement="end"
          justify="start"
          :checked="trust"
          :disabled="submitting"
          @ion-change="trust = $event.detail.checked"
        >
          {{ $t('accounts.twoFactor.trust') }}
        </ion-checkbox>
        <p
          class="trust-hint"
          data-testid="mfa-trust-hint"
        >
          {{ $t('accounts.twoFactor.trustHint') }}
        </p>
      </div>
      <ion-button
        type="submit"
        data-testid="mfa-submit"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        :disabled="submitting"
      >
        {{ step === 'trust' ? $t('accounts.twoFactor.continue') : $t('accounts.twoFactor.verify') }}
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
<style scoped>
.trust {
  margin-top: 14px;
}
.trust ion-checkbox {
  --size: 20px;
  width: 100%;
  font-size: 14px;
}
/* The label wraps on a phone instead of being cut. */
.trust ion-checkbox::part(label) {
  white-space: normal;
}
.trust-hint {
  margin: 4px 0 0 32px;
  font-size: 12px;
  color: var(--ion-color-medium);
}
</style>
