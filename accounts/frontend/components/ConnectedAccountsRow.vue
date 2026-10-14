<script setup lang="ts">
// The «Google» row of Account → Security, «Sign-in» (mockups `account.html` «security»; U-63): the Google account
// the person can sign in with (allauth.headless `account/providers`) and «Disconnect», confirmed with what changes;
// or, unlinked, «Connect»: the provider's handshake as a synchronous form post (`process=connect`), which comes back
// to this tab. Google being the only way in (no password: allauth refuses with `no_password`) keeps «Disconnect»
// off and says to create a password first. Without Google on the server (`spa-config.googleEnabled`) and nothing
// linked, there is no row. allauth may ask «Confirm it's you» before disconnecting (ReauthModal).
import { ConfirmDialog } from '@erplora/ui/components';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { ApiError, createAllauthClient, type ProviderAccount, type ProviderRedirectForm, useLiveClient } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed, nextTick, onMounted, shallowRef, useTemplateRef } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../error-text';
import { reauthRequestOf, useReauthentication } from '../reauth';
import ReauthModal from './ReauthModal.vue';

const props = defineProps<{
  /** The account has a password: without one, Google is its only way in. */
  hasPassword: boolean;
}>();

const GOOGLE = 'google';
/** Where the handshake comes back: this tab. */
const BACK_HERE = '/account/security';

const { t } = useI18n();
const { forDialog } = useErrorText();
const client = useLiveClient();
const auth = createAllauthClient(client.config);
const reauth = useReauthentication();
const googleEnabled = client.config.googleEnabled === true;

const accounts = shallowRef<ProviderAccount[] | null>(null);
const google = computed(() => accounts.value?.find((account) => account.provider.id === GOOGLE) ?? null);
/** Google is the only way to sign in: no password and no other linked account. */
const onlyWayIn = computed(() => !props.hasPassword && (accounts.value?.length ?? 0) <= 1);
const shown = computed(() => accounts.value !== null && (google.value !== null || googleEnabled));

onMounted(async () => {
  try {
    accounts.value = await auth.providerAccounts();
  } catch {
    // Not read: no row rather than a wrong one (Security still works without it).
    accounts.value = null;
  }
});

const confirming = shallowRef(false);
const pending = shallowRef(false);
const failure = shallowRef<ApiError | null>(null);

function ask(): void {
  failure.value = null;
  confirming.value = true;
}

async function disconnect(): Promise<void> {
  const linked = google.value;
  if (!linked) return;
  pending.value = true;
  failure.value = null;
  try {
    const left = await reauth.guard(() => auth.disconnectProvider(GOOGLE, linked.uid));
    if (!left) return;
    accounts.value = left;
    confirming.value = false;
    void toastSuccess(t('accounts.account.google.disconnected'));
  } catch (error) {
    if (!reauthRequestOf(error)) failure.value = error instanceof ApiError ? error : new ApiError(0, 'client_error', String(error));
  } finally {
    pending.value = false;
  }
}

const redirect = shallowRef<ProviderRedirectForm | null>(null);
const connectForm = useTemplateRef<HTMLFormElement>('connectForm');

async function connect(): Promise<void> {
  redirect.value = auth.providerRedirectForm({ provider: GOOGLE, callbackUrl: BACK_HERE, process: 'connect' });
  await nextTick();
  connectForm.value?.submit();
}
</script>

<template>
  <div
    v-if="shown"
    class="card-row"
    data-testid="google-row"
  >
    <div class="card-row__text">
      <h3 class="card-row__title">
        Google
      </h3>
      <p class="card-text">
        {{ google ? $t('accounts.account.google.connected', { account: google.display }) : $t('accounts.account.google.notConnected') }}
      </p>
      <p
        v-if="google && onlyWayIn"
        class="card-text"
      >
        {{ $t('accounts.account.google.onlyWayIn') }}
      </p>
    </div>
    <ion-button
      v-if="google"
      data-testid="google-disconnect"
      fill="outline"
      :disabled="onlyWayIn"
      @click="ask"
    >
      <HubIcon
        slot="start"
        name="lucide:unlink"
        aria-hidden="true"
      />
      {{ $t('accounts.account.google.disconnect') }}
    </ion-button>
    <ion-button
      v-else
      data-testid="google-connect"
      fill="outline"
      @click="connect"
    >
      <HubIcon
        slot="start"
        name="ion:logo-google"
        aria-hidden="true"
      />
      {{ $t('accounts.account.google.connect') }}
    </ion-button>
  </div>
  <form
    v-if="redirect"
    ref="connectForm"
    data-testid="google-connect-form"
    :method="redirect.method"
    :action="redirect.action"
    hidden
  >
    <input
      v-for="(value, name) in redirect.fields"
      :key="name"
      type="hidden"
      :name="name"
      :value="value"
    >
  </form>
  <ConfirmDialog
    v-model:open="confirming"
    testid="disconnect-google"
    confirm-icon="lucide:unlink"
    :title="$t('accounts.account.google.disconnectTitle')"
    :message="$t('accounts.account.google.disconnectMessage', { account: google?.display ?? '' })"
    :confirm-label="$t('accounts.account.google.disconnect')"
    :pending="pending"
    :error="forDialog(failure)"
    @confirm="disconnect"
  />
  <ReauthModal
    :request="reauth.request.value"
    @confirmed="reauth.confirmed"
    @cancel="reauth.cancelled"
  />
</template>

<style scoped src="./account-card.css"></style>
