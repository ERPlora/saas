<script setup lang="ts">
// The SaaS's sign-in, over allauth.headless (browser client): the page of
// `templates/account/login.html`, same structure and texts (its msgids, `../locale`), in the auth
// frame of every account screen (`AuthShell`). A rejected login paints each message under its
// input; a signed-in visitor leaves the SPA for `next` (a path of this site, e.g. the jump to a
// hub, a Django page) or the launcher, with a full page load that brings the new session.
//
// «Continue with Google» stays the Django route `/auth/google/login/` (the redirect URIs registered
// with Google): a plain form POST, which a Vue page can submit as any page does, carrying Django's
// CSRF token from the cookie and the destination. «Keep me signed in» is not here: allauth.headless
// takes no `remember`, so the session lasts SESSION_COOKIE_AGE. A login that waits for its second
// factor goes on to `/2fa/authenticate`, carrying `next`.
import { ApiError, createAllauthClient, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonInput, IonInputPasswordToggle } from '@ionic/vue';
import { computed, onMounted, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import { localNext } from '../next';

const LAUNCHER = '/launch';
const PASSWORD_RESET = '/accounts/password/reset/';
const GOOGLE_LOGIN = '/auth/google/login/';
const TWO_FACTOR = '/2fa/authenticate';
/** allauth's flow of a login that waits for its second factor. */
const SECOND_FACTOR_FLOW = 'mfa_authenticate';
const NON_FIELD = '__all__';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();
const client = useLiveClient();
const auth = createAllauthClient(client.config);

const googleEnabled = client.config.googleEnabled === true;
const csrfToken = auth.csrfToken() ?? '';

const email = shallowRef('');
const password = shallowRef('');
const submitting = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

const next = computed(() => localNext(route.query.next));

const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

function leave(): void {
  location.assign(next.value ?? LAUNCHER);
}

// The template login sends a visitor who is already signed in on at once; so does this page.
watch(session.user, (user) => user && leave(), { immediate: true });

onMounted(() => {
  document.title = `${t('accounts.login.title')} - ERPlora Cloud`;
});

async function submit(): Promise<void> {
  submitting.value = true;
  fields.value = {};
  failure.value = '';
  try {
    const state = await auth.login({ email: email.value, password: password.value });
    if (state.authenticated) {
      leave();
    } else if (state.pendingFlow === SECOND_FACTOR_FLOW) {
      await router.push({ path: TWO_FACTOR, query: next.value ? { next: next.value } : {} });
    } else {
      // Any other further step (email verification) has no page in this SPA yet.
      failure.value = t('accounts.login.failed');
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      leave(); // Signed in meanwhile (another tab): nothing left to do here.
    } else if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else {
      failure.value = t('accounts.login.failed');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AuthShell :subtitle="$t('accounts.login.subtitle')">
    <p class="intro">
      {{ $t('accounts.login.intro') }}
    </p>

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
        <a
          data-testid="login-forgot"
          :href="PASSWORD_RESET"
        >{{ $t('accounts.login.forgotPassword') }}</a>
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
        method="post"
        :action="GOOGLE_LOGIN"
      >
        <input
          type="hidden"
          name="csrfmiddlewaretoken"
          :value="csrfToken"
        >
        <input
          v-if="next"
          type="hidden"
          name="next"
          :value="next"
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

    <template #foot>
      <p class="foot">
        {{ $t('accounts.login.agree') }}
        <a href="https://erplora.com/legal/terms/">{{ $t('accounts.login.terms') }}</a>
        &amp;
        <a href="https://erplora.com/legal/privacy/">{{ $t('accounts.login.privacy') }}</a>.
      </p>
    </template>
  </AuthShell>
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
.row-end a,
.foot a {
  color: var(--ion-color-primary);
}
.row-end a:hover,
.foot a:hover {
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
.foot {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  color: color-mix(in oklch, var(--ion-text-color) 45%, transparent);
  text-align: center;
}
</style>
