<script setup lang="ts">
// «Sign out of erplora.com?» (`/logout`, ACCOUNTS-F09): where the Hub's «Sign out» lands on a device without the PIN
// pad (BASE-F61, hub `base/auth_views.py`), as the old SaaS's allauth page `account/logout.html` did. The Hub has
// already ended its own session; erplora.com's stays open in this browser until the person confirms here, as an
// identity provider asks when an app sends someone to its sign-out (OpenID Connect RP-Initiated Logout, Keycloak,
// allauth). Opening the page closes nothing: a loose link, or another site's `<img>`, never signs anybody out.
// «Sign out» ends the session with allauth.headless (`DELETE …/auth/session`) and loads the launcher, as the user
// menu does (`frontend/main.ts`); a failure says so and stays. «Stay signed in» goes to the launcher with the session
// as it was. Without a session there is nothing to close: the launcher's sign-in at once.
import { createAllauthClient, useLiveClient } from '@erplora/ui/sdk';
import { ionIconSrc, useSession } from '@erplora/ui/shell';
import { IonButton, IonIcon } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import { LAUNCHER } from '../paths';

const ICON = ionIconSrc('ion:log-out-outline');

const { t } = useI18n();
const router = useRouter();
const session = useSession();
const auth = createAllauthClient(useLiveClient().config);

const account = computed(() => session.user.value?.email || session.user.value?.label || '');
const signingOut = shallowRef(false);
const failure = shallowRef('');

if (!session.user.value) void router.replace(LAUNCHER);

onMounted(() => {
  document.title = `${t('accounts.signOut.title')} - ERPlora Cloud`;
});

async function signOut(): Promise<void> {
  signingOut.value = true;
  failure.value = '';
  try {
    const state = await auth.logout();
    if (state.authenticated) throw new Error('still signed in after signing out');
    location.assign(LAUNCHER);
  } catch (error) {
    console.error('saas: sign out failed', error);
    failure.value = t('accounts.signOut.failed');
    signingOut.value = false;
  }
}
</script>

<template>
  <AuthShell :subtitle="$t('accounts.login.subtitle')">
    <div class="auth-mark">
      <ion-icon
        class="auth-mark-icon"
        :icon="ICON"
        aria-hidden="true"
      />
    </div>
    <h2 class="auth-title">
      {{ $t('accounts.signOut.title') }}
    </h2>
    <p
      class="auth-lead"
      data-testid="sign-out-lead"
    >
      {{ $t('accounts.signOut.lead', { account }) }}
    </p>
    <div
      v-if="failure"
      class="non-field-error"
      role="alert"
    >
      {{ failure }}
    </div>
    <ion-button
      data-testid="sign-out-confirm"
      color="primary"
      size="large"
      expand="block"
      class="submit"
      :disabled="signingOut"
      @click="signOut"
    >
      {{ $t('accounts.signOut.confirm') }}
    </ion-button>
    <ion-button
      data-testid="sign-out-stay"
      fill="outline"
      expand="block"
      class="after"
      :disabled="signingOut"
      @click="router.replace(LAUNCHER)"
    >
      {{ $t('accounts.signOut.stay') }}
    </ion-button>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
