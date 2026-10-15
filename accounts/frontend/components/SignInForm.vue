<script setup lang="ts">
// The form of the launcher (`/launch`, the entrance; Ioan, 2026-10-15), over allauth.headless (browser client,
// headless only): the form of the old template login (ERPlora/saas `templates/account/login.html`), same
// structure and texts (its msgids, `../locale`). The frame is the page's (`AuthShell`, as the template's). A
// rejected login or sign-up paints each message under its input.
//
// Two strict tabs over the same email and password, as the market does (FIX-LAUNCH-TABS): «Sign in», the
// default, is allauth's login and never creates an account; «Create account» (`?tab=signup`, the address the
// old sign-up pages lead to) is allauth's sign-up and never signs in. allauth answers an unknown address as a
// wrong password, and an address already held as a new one: neither tab tells which addresses hold an
// account. The tab is in the address (`router.replace`, keeping `next`), so a link opens either.
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
import { IonButton, IonIcon, IonInput, IonInputPasswordToggle, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, onMounted, shallowRef, watch } from 'vue';
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
/** allauth's code of a refused login: a wrong password and an unknown address alike. */
const MISMATCH = 'email_password_mismatch';

type Tab = 'signin' | 'signup';
/** `?tab=` of «Create account»; «Sign in» has none. */
const SIGN_UP: Tab = 'signup';
const SIGN_IN: Tab = 'signin';
const TABS: readonly Tab[] = [SIGN_IN, SIGN_UP];
/** What changes with the tab: the words, the browser's password autofill and the request. */
const TEXTS: Record<Tab, { label: string; intro: string; failed: string; switchLead: string; switchAction: string }> = {
  signin: {
    label: 'accounts.login.signIn',
    intro: 'accounts.login.introSignIn',
    failed: 'accounts.login.failed',
    switchLead: 'accounts.login.firstTime',
    switchAction: 'accounts.login.createYourAccount',
  },
  signup: {
    label: 'accounts.login.signUp',
    intro: 'accounts.login.introSignUp',
    failed: 'accounts.login.signUpFailed',
    switchLead: 'accounts.login.haveAccount',
    switchAction: 'accounts.login.signInInstead',
  },
};

const tabOf = (value: unknown): Tab => (value === SIGN_UP ? SIGN_UP : SIGN_IN);

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
/** The failure is a wrong email or password: «Sign in» then offers «Create account». */
const mismatch = shallowRef(false);
const tab = shallowRef<Tab>(tabOf(route.query.tab));
const texts = computed(() => TEXTS[tab.value]);
const other = computed<Tab>(() => (tab.value === SIGN_UP ? SIGN_IN : SIGN_UP));

const next = computed(() => localNext(route.query.next));
const keepNext = computed(() => (next.value ? { next: next.value } : {}));
const google = computed(() =>
  auth.providerRedirectForm({ provider: GOOGLE, callbackUrl: next.value ?? LAUNCHER, process: 'login' }),
);
const notice = computed(() => (typeof route.query.notice === 'string' ? NOTICES[route.query.notice] : undefined));

// The address leads (a link of the page, the way back): the form follows it.
watch(
  () => route.query.tab,
  (value) => {
    tab.value = tabOf(value);
  },
);
// A tab starts clean: the errors of the other one are not its own.
watch(tab, clearErrors);

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

function clearErrors(): void {
  fields.value = {};
  failure.value = '';
  mismatch.value = false;
}

/** Shows the chosen tab and writes it in the address, keeping the rest of the query (`next`). */
function chooseTab(value: unknown): void {
  const chosen = tabOf(value);
  tab.value = chosen;
  const query = { ...route.query };
  delete query.tab;
  void router.replace({ path: route.path, query: chosen === SIGN_UP ? { ...query, tab: SIGN_UP } : query });
}

async function submit(): Promise<void> {
  submitting.value = true;
  clearErrors();
  const credentials = { email: email.value, password: password.value };
  try {
    const state = tab.value === SIGN_UP ? await auth.signup(credentials) : await auth.login(credentials);
    if (state.authenticated) {
      leave();
    } else if (state.pendingFlow === SECOND_FACTOR_FLOW) {
      await router.push({ path: TWO_FACTOR, query: keepNext.value });
    } else if (state.pendingFlow && MAILED_CODE_FLOWS.includes(state.pendingFlow)) {
      await router.push({ path: MAILED_CODE, query: keepNext.value, state: { email: email.value, flow: state.pendingFlow } });
    } else {
      // Any other further step has no page in this SPA.
      failure.value = t(texts.value.failed);
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      leave(); // Signed in meanwhile (another tab): nothing left to do here.
    } else if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
      mismatch.value = tab.value === SIGN_IN && error.code === MISMATCH;
    } else if (error instanceof ApiError && error.status === 429) {
      failure.value = t('accounts.login.tooManyAttempts');
    } else {
      failure.value = t(texts.value.failed);
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <ion-segment
    data-testid="login-tabs"
    class="tabs"
    :value="tab"
    :aria-label="$t('accounts.login.tabsLabel')"
    @ion-change="chooseTab($event.detail.value)"
  >
    <ion-segment-button
      v-for="value in TABS"
      :key="value"
      :value="value"
      :data-testid="`login-tab-${value}`"
    >
      <ion-label>{{ $t(TEXTS[value].label) }}</ion-label>
    </ion-segment-button>
  </ion-segment>

  <p class="intro">
    {{ $t(texts.intro) }}
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
        :autocomplete="tab === SIGN_UP ? 'new-password' : 'current-password'"
        required
        :error-text="fields.password"
        :class="invalid('password')"
      >
        <ion-input-password-toggle slot="end" />
      </ion-input>
    </div>

    <!-- Under the error of a wrong email or password (an unknown address answers the same). -->
    <p
      v-if="mismatch"
      class="hint"
      data-testid="login-error-signup"
    >
      {{ $t('accounts.login.firstTime') }}
      <button
        type="button"
        class="link"
        @click="chooseTab(SIGN_UP)"
      >
        {{ $t('accounts.login.createYourAccount') }}
      </button>
    </p>

    <div
      v-if="tab === SIGN_IN"
      class="row-end"
    >
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
      {{ $t(texts.label) }}
    </ion-button>

    <p
      class="switch"
      data-testid="login-switch"
    >
      {{ $t(texts.switchLead) }}
      <button
        type="button"
        class="link"
        data-testid="login-switch-action"
        @click="chooseTab(other)"
      >
        {{ $t(texts.switchAction) }}
      </button>
    </p>
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
/* The tabs: a grey track with the chosen one on a raised pill, as the Account page's appearance switch. */
.tabs {
  --background: color-mix(in oklab, var(--ion-text-color) 7%, transparent);
  border-radius: 12px;
  margin: 0 0 1rem;
}
/* A 44 px target, also with a mouse: the two ways in are the page's first choice. */
.tabs ion-segment-button {
  min-height: 44px;
  text-transform: none;
}
.tabs ion-segment-button::part(indicator-background) {
  background: var(--ion-card-background, #fff);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}
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
.switch {
  margin: 1rem 0 0;
  text-align: center;
  font-size: 13px;
  color: color-mix(in oklch, var(--ion-text-color) 60%, transparent);
}
.hint {
  margin: 0.5rem 0 0;
  font-size: 13px;
  color: color-mix(in oklch, var(--ion-text-color) 60%, transparent);
}
/* A text link that is a button (it changes the tab, it goes nowhere), padded to the 44 px a finger needs. */
.link {
  appearance: none;
  background: none;
  border: 0;
  font: inherit;
  color: var(--ion-color-primary);
  cursor: pointer;
  padding: 12px 0;
  margin: -12px 0;
}
.link:hover {
  text-decoration: underline;
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
