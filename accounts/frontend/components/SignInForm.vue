<script setup lang="ts">
// The one form that signs in and signs up, in the launcher (`/launch`, the entrance; Ioan, 2026-10-15),
// over allauth.headless (browser client, headless only): the form of the old template login (ERPlora/saas
// `templates/account/login.html`), same structure and texts (its msgids, `../locale`). The frame is the
// page's (`AuthShell`, as the template's). A rejected login paints each message under its input.
//
// It is the sign-up too («New here? We'll create your account»): an unknown address creates the account.
// Every password sign-in then waits for a code mailed to the account, typed at `/verify-email`, which gets
// the typed address in the history state (never in the URL): the one that proves a new (or never proven)
// address (`verify_email`), or the sign-in code of every other account (`login_by_code`, the second factor
// by email), and which of the two in the same state. A login that waits for the authenticator app goes on to `/2fa/authenticate`: after the
// password, or on arrival, when Google came back with the login waiting. «Forgot your password?» is the
// SPA's `/password/reset`, which comes back here with `?notice=password_reset` once it is changed; the
// code page comes back with `?notice=code_expired` when the code is gone.
//
// Signed in, the SPA is loaded again with the new session: `next` (a path of this site, e.g. the jump to a
// hub, a Django page) or the launcher. «Continue with Google» is allauth.headless's provider redirect, a
// plain form POST (Django's CSRF token from the cookie) that comes back to the same place; Google itself
// comes back to the redirect URI registered with it, `/auth/google/callback/`.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, createAllauthClient, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonIcon, IonInput, IonInputPasswordToggle } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import { localNext } from '../next';
import { LAUNCHER } from '../paths';

const PASSWORD_RESET = '/password/reset';
const GOOGLE = 'google';
const TWO_FACTOR = '/2fa/authenticate';
const MAILED_CODE = '/verify-email';
/** allauth's flow of a login that waits for the authenticator app. */
const SECOND_FACTOR_FLOW = 'mfa_authenticate';
/** allauth's flows of a login that waits for a code mailed to the account: both are typed at `/verify-email`. */
const MAILED_CODE_FLOWS = ['verify_email', 'login_by_code'];
/** `?notice=` of a page that sends the visitor here: what it says, and in which tone. */
const NOTICES: Record<string, { text: string; tone: 'success' | 'warning' }> = {
  // The reset page, once the password is changed.
  password_reset: { text: 'accounts.passwordReset.done', tone: 'success' },
  // The code page, when the mailed code expired or was typed wrong too many times.
  code_expired: { text: 'accounts.login.codeExpired', tone: 'warning' },
};
const NON_FIELD = '__all__';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const client = useLiveClient();
const auth = createAllauthClient(client.config);

const googleEnabled = client.config.googleEnabled === true;

const email = shallowRef('');
const password = shallowRef('');
const submitting = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

const next = computed(() => localNext(route.query.next));
const keepNext = computed(() => (next.value ? { next: next.value } : {}));
const google = computed(() =>
  auth.providerRedirectForm({ provider: GOOGLE, callbackUrl: next.value ?? LAUNCHER, process: 'login' }),
);
const notice = computed(() => (typeof route.query.notice === 'string' ? NOTICES[route.query.notice] : undefined));

const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

/** A full load of `next` or the launcher: the page reads the new session from the HTML. */
function leave(): void {
  location.assign(next.value ?? LAUNCHER);
}

/** A login waiting for its second factor (back from Google) goes on to the code, as the template resumed it. */
async function resumeWaitingLogin(): Promise<void> {
  try {
    const state = await auth.getSession();
    if (!state.authenticated && state.pendingFlow === SECOND_FACTOR_FLOW) {
      await router.replace({ path: TWO_FACTOR, query: keepNext.value });
    }
  } catch {
    // Unread, the form stays: signing in again starts a new login.
  }
}

onMounted(() => void resumeWaitingLogin());

async function submit(): Promise<void> {
  submitting.value = true;
  fields.value = {};
  failure.value = '';
  try {
    const state = await auth.login({ email: email.value, password: password.value });
    if (state.authenticated) {
      leave();
    } else if (state.pendingFlow === SECOND_FACTOR_FLOW) {
      await router.push({ path: TWO_FACTOR, query: keepNext.value });
    } else if (state.pendingFlow && MAILED_CODE_FLOWS.includes(state.pendingFlow)) {
      await router.push({ path: MAILED_CODE, query: keepNext.value, state: { email: email.value, flow: state.pendingFlow } });
    } else {
      // Any other further step has no page in this SPA.
      failure.value = t('accounts.login.failed');
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      leave(); // Signed in meanwhile (another tab): nothing left to do here.
    } else if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else if (error instanceof ApiError && error.status === 429) {
      failure.value = t('accounts.login.tooManyAttempts');
    } else {
      failure.value = t('accounts.login.failed');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <p class="intro">
    {{ $t('accounts.login.intro') }}
  </p>

  <InlineFeedback
    v-if="notice"
    :tone="notice.tone"
    class="notice"
    data-testid="login-notice"
  >
    {{ $t(notice.text) }}
  </InlineFeedback>

  <form
    data-testid="login-form"
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
        data-testid="login-email"
        mode="md"
        type="email"
        :label="$t('accounts.login.email')"
        label-placement="floating"
        fill="outline"
        placeholder="you@example.com"
        autocomplete="username"
        required
        :error-text="fields.email"
        :class="invalid('email')"
      />
    </div>

    <div class="field">
      <ion-input
        v-model="password"
        data-testid="login-password"
        mode="md"
        type="password"
        :label="$t('accounts.login.password')"
        label-placement="floating"
        fill="outline"
        placeholder="••••••••••"
        autocomplete="current-password"
        required
        :error-text="fields.password"
        :class="invalid('password')"
      >
        <ion-input-password-toggle slot="end" />
      </ion-input>
    </div>

    <div class="row-end">
      <router-link
        data-testid="login-forgot"
        :to="PASSWORD_RESET"
      >
        {{ $t('accounts.login.forgotPassword') }}
      </router-link>
    </div>

    <ion-button
      type="submit"
      data-testid="login-submit"
      color="primary"
      size="large"
      expand="block"
      class="submit"
      :disabled="submitting"
    >
      {{ $t('accounts.login.continue') }}
    </ion-button>
  </form>

  <template v-if="googleEnabled">
    <div class="divider">
      <span class="divider-line" />
      {{ $t('accounts.login.or') }}
      <span class="divider-line" />
    </div>
    <form
      data-testid="login-google"
      :method="google.method"
      :action="google.action"
    >
      <input
        v-for="(value, name) in google.fields"
        :key="name"
        type="hidden"
        :name="name"
        :value="value"
      >
      <ion-button
        type="submit"
        fill="outline"
        size="large"
        expand="block"
      >
        <ion-icon
          name="logo-google"
          class="google-icon"
          aria-hidden="true"
        />
        <span class="google-label">{{ $t('accounts.login.continueWithGoogle') }}</span>
      </ion-button>
    </form>
  </template>
</template>

<style scoped>
/* Ported from `templates/account/_auth_styles.html` (the login's part of it; the frame is AuthShell's). */
.intro {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 13px;
  color: color-mix(in oklch, var(--ion-text-color) 45%, transparent);
  text-align: center;
  margin: 0 0 1rem;
}
.notice {
  margin-bottom: 0.85rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.field + .field {
  margin-top: 0.85rem;
}
.row-end {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-top: 1rem;
  font-size: 13px;
}
.row-end a {
  color: var(--ion-color-primary);
  /* A link of one line of 13 px: padded to the 44 px a finger needs, without moving the layout. */
  padding: 12px 0;
  margin: -12px 0;
}
.row-end a:hover {
  text-decoration: underline;
}
.submit {
  margin-top: 1.25rem;
}
.non-field-error {
  margin-bottom: 0.85rem;
  padding: 0.65rem 0.85rem;
  border: 1px solid color-mix(in oklch, var(--ion-color-danger) 35%, transparent);
  background: color-mix(in oklch, var(--ion-color-danger) 8%, transparent);
  color: var(--ion-color-danger);
  border-radius: 0.5rem;
  font-size: 13px;
}
.divider {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1.25rem 0 0.75rem;
  color: color-mix(in oklch, var(--ion-text-color) 45%, transparent);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.divider-line {
  flex: 1;
  height: 1px;
  background: color-mix(in oklch, var(--ion-text-color) 14%, transparent);
}
/* The template's Iconify icon was 1em of the button's text: ion-button gives a slotted ion-icon 1.35em. */
.google-icon {
  font-size: 1em;
}
.google-label {
  margin-inline-start: 0.5rem;
}
</style>
