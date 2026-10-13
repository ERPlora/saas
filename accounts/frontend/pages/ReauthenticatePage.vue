<script setup lang="ts">
// «Confirm it's you» (`/reauthenticate`), over allauth.headless: the step before changing the
// sign-in security, when allauth asks for a recent login (`reauthentication_required`). The pages
// of `templates/account/reauthenticate.html` (password) and `mfa/reauthenticate.html` (a code
// from the authenticator app or a recovery code) in one card, same structure and texts:
// `?flows=` (allauth's flow ids, comma-separated) lists the allowed ways and only those are offered,
// as the templates' «alternatives» did (without it, both); `?method=totp|password` picks the first
// one among them (default the password, or the code when it is the only way).
// Confirmed → `next` (a path of this site, `/2fa` by default) with a full page load, as the sign-in
// leaves: `next` can be a Django route (`/hub-login/` sends here when the jump needs it).
import { ApiError, createAllauthClient, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonInput, IonInputPasswordToggle } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import CodeField from '../components/CodeField.vue';
import { localNext } from '../next';

type Method = 'password' | 'totp';

/** The 2FA settings: where a reauthentication usually comes from, and the foot's way back. */
const SETTINGS = '/2fa';
const LOGIN = '/login';
/** allauth's flows that confirm a recent login: the password, the authenticator (or a recovery code). */
const PASSWORD_FLOW = 'reauthenticate';
const CODE_FLOW = 'mfa_reauthenticate';
const NON_FIELD = '__all__';
const ICONS: Record<Method, string | undefined> = {
  password: ionIconSrc('lucide:lock'),
  totp: ionIconSrc('lucide:shield-check'),
};

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = createAllauthClient(useLiveClient().config);

const FLOW_OF: Record<Method, string> = { password: PASSWORD_FLOW, totp: CODE_FLOW };

const offered = computed(() => {
  const flows = route.query.flows;
  return typeof flows === 'string' ? new Set(flows.split(',')) : new Set([PASSWORD_FLOW, CODE_FLOW]);
});
const isOffered = (way: Method) => offered.value.has(FLOW_OF[way]);
const otherThan = (way: Method): Method => (way === 'password' ? 'totp' : 'password');

/** `?method=` (the password by default) when allauth allows it, else the other way. */
function firstMethod(): Method {
  const asked: Method = route.query.method === 'totp' ? 'totp' : 'password';
  return isOffered(asked) || !isOffered(otherThan(asked)) ? asked : otherThan(asked);
}

const method = shallowRef<Method>(firstMethod());
const password = shallowRef('');
const code = shallowRef('');
const submitting = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

const next = computed(() => localNext(route.query.next) ?? SETTINGS);
/** The other way to confirm, when allauth offers it. */
const alternative = computed<Method | null>(() => (isOffered(otherThan(method.value)) ? otherThan(method.value) : null));

const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

onMounted(() => {
  document.title = `${t('accounts.reauthenticate.title')} - ERPlora Cloud`;
});

function use(other: Method): void {
  method.value = other;
  fields.value = {};
  failure.value = '';
}

async function submit(): Promise<void> {
  submitting.value = true;
  fields.value = {};
  failure.value = '';
  try {
    if (method.value === 'totp') await auth.mfaReauthenticate(code.value);
    else await auth.reauthenticate(password.value);
    location.assign(next.value);
  } catch (error) {
    if (error instanceof ApiError && error.code === 'not_authenticated') {
      // The session ended meanwhile: sign in again and come back here.
      await router.replace({ path: LOGIN, query: { next: route.fullPath } });
    } else if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else {
      failure.value = t('accounts.twoFactor.failed');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AuthShell :subtitle="$t('accounts.reauthenticate.subtitle')">
    <div class="auth-mark">
      <ion-icon
        class="auth-mark-icon"
        :icon="ICONS[method]"
        aria-hidden="true"
      />
    </div>
    <h2 class="auth-title">
      {{ $t('accounts.reauthenticate.title') }}
    </h2>
    <p
      class="auth-lead"
      data-testid="reauth-lead"
    >
      {{ method === 'totp' ? $t('accounts.reauthenticate.codeLead') : $t('accounts.reauthenticate.passwordLead') }}
    </p>

    <div
      v-if="failure"
      class="non-field-error"
      role="alert"
    >
      {{ failure }}
    </div>

    <form
      data-testid="reauth-form"
      novalidate
      @submit.prevent="submit"
    >
      <CodeField
        v-if="method === 'totp'"
        v-model="code"
        :error="fields.code"
      />
      <div
        v-else
        class="field"
      >
        <ion-input
          v-model="password"
          data-testid="reauth-password"
          mode="md"
          type="password"
          :label="$t('accounts.reauthenticate.password')"
          label-placement="floating"
          fill="outline"
          placeholder="••••••••••"
          autocomplete="current-password"
          :required="true"
          :error-text="fields.password"
          :class="invalid('password')"
        >
          <ion-input-password-toggle slot="end" />
        </ion-input>
      </div>

      <ion-button
        type="submit"
        data-testid="reauth-submit"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        :disabled="submitting"
      >
        {{ $t('accounts.reauthenticate.confirm') }}
      </ion-button>
    </form>

    <template v-if="alternative">
      <p
        class="auth-lead alternatives"
        data-testid="reauth-alternative-lead"
      >
        {{ method === 'totp' ? $t('accounts.reauthenticate.cantUseAuthenticator') : $t('accounts.reauthenticate.cantUsePassword') }}
      </p>
      <ion-button
        v-if="alternative === 'totp'"
        data-testid="reauth-use-authenticator"
        fill="outline"
        expand="block"
        class="after"
        @click="use('totp')"
      >
        {{ $t('accounts.reauthenticate.useAuthenticator') }}
      </ion-button>
      <ion-button
        v-else
        data-testid="reauth-use-password"
        fill="outline"
        expand="block"
        class="after"
        @click="use('password')"
      >
        {{ $t('accounts.reauthenticate.usePassword') }}
      </ion-button>
    </template>

    <template #foot>
      <p class="foot">
        <router-link :to="SETTINGS">
          {{ $t('accounts.reauthenticate.backToSettings') }}
        </router-link>
      </p>
    </template>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
