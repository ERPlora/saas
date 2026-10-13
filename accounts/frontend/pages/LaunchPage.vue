<script setup lang="ts">
// The launcher (`/launch`), the entry of erplora.com (PLAN-SAAS §3.1 step 4): the page of
// `accounts/launch.html` and the view `handoff.launch`, same texts (their msgids, `../locale`). It
// reads the account's hubs (`accounts.hub.list`): with ONE it jumps straight to it, with several it
// lists them, with none it says so. The jump is `/hub-login/`, a Django page (the form that posts
// the one-time code to the hub), so it is always a full navigation. «Sign Out» posts Django's
// logout form, as the template did, and lands on the sign-in. `?notice=mfa_unavailable` (the 2FA
// settings, with 2FA switched off on the server) says so above the hubs, and then a single hub is
// listed instead of jumped to, or the notice would never be read.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { isUnauthorized, type OutputOf, readCookie, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonItem, IonLabel, IonList, IonSpinner } from '@ionic/vue';
import { onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';

type Hub = OutputOf<'accounts.hub.list'>['hubs'][number];

const HERE = '/launch';
const LOGIN = '/login';
const LOGOUT = '/accounts/logout/';

const { t } = useI18n();
const route = useRoute();
const client = useLiveClient();
const csrfToken = readCookie(document.cookie, client.config.csrfCookieName) ?? '';

const status = shallowRef<'loading' | 'ready' | 'error'>('loading');
const hubs = shallowRef<Hub[]>([]);
const opening = shallowRef(false);
const mfaUnavailable = route.query.notice === 'mfa_unavailable';

function open(hub: Hub): void {
  opening.value = true;
  location.assign(hub.url);
}

async function load(): Promise<void> {
  status.value = 'loading';
  try {
    hubs.value = (await client.api.call('accounts.hub.list', {})).hubs;
    status.value = 'ready';
    // One hub: nothing to choose, as the template view did (unless there is a notice to read).
    if (hubs.value.length === 1 && !mfaUnavailable) open(hubs.value[0]);
  } catch (error) {
    // The session ended after the page was served: sign in again and come back.
    if (isUnauthorized(error)) location.assign(`${LOGIN}?next=${encodeURIComponent(HERE)}`);
    else status.value = 'error';
  }
}

onMounted(() => {
  document.title = `${t('accounts.launch.title')} - ERPlora Cloud`;
  void load();
});
</script>

<template>
  <AuthShell :subtitle="$t('accounts.launch.title')">
    <InlineFeedback
      v-if="mfaUnavailable"
      tone="info"
      class="notice"
      data-testid="launch-notice"
    >
      {{ $t('accounts.launch.mfaUnavailable') }}
    </InlineFeedback>

    <div
      v-if="status === 'loading' || opening"
      class="ion-text-center"
      data-testid="launch-loading"
    >
      <ion-spinner name="crescent" />
      <p
        v-if="opening"
        class="auth-lead"
      >
        {{ $t('accounts.launch.opening') }}
      </p>
    </div>

    <InlineFeedback
      v-else-if="status === 'error'"
      tone="danger"
      data-testid="launch-error"
    >
      {{ $t('accounts.launch.loadError') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          @click="load()"
        >
          {{ $t('accounts.launch.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <ion-list
      v-else-if="hubs.length"
      lines="full"
      data-testid="launch-hubs"
    >
      <ion-item
        v-for="hub in hubs"
        :key="hub.slug"
        :href="hub.url"
        :detail="true"
      >
        <ion-label>
          <h2>{{ hub.slug }}</h2>
          <p>{{ hub.host }}</p>
        </ion-label>
      </ion-item>
    </ion-list>

    <EmptyState
      v-else
      data-testid="launch-empty"
      icon="storefront-outline"
      :message="$t('accounts.launch.noHubs')"
    />

    <form
      data-testid="launch-logout"
      method="post"
      :action="LOGOUT"
    >
      <input
        type="hidden"
        name="csrfmiddlewaretoken"
        :value="csrfToken"
      >
      <input
        type="hidden"
        name="next"
        :value="LOGIN"
      >
      <ion-button
        type="submit"
        fill="clear"
        expand="block"
        class="logout"
      >
        {{ $t('accounts.launch.signOut') }}
      </ion-button>
    </form>
  </AuthShell>
</template>

<style scoped>
/* `launch.html`: «Sign Out» 1rem under the list. */
.notice {
  margin-bottom: 1rem;
}
.logout {
  margin-top: 1rem;
}
</style>
