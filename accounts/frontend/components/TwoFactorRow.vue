<script setup lang="ts">
// Account → Security, the «Two-step verification» row of «Sign-in» (mockups `account.html` «security»): whether the
// account asks for a code of an authenticator app after its password (allauth.headless `account/authenticators`)
// and the way to its settings, the `/2fa` page. With 2FA switched off on the server (`ACCOUNTS_MFA_ENABLED`: its
// endpoints answer 404, as TwoFactorSettingsPage reads it) there is nothing to manage: the row is not painted, and
// when `spa-config.mfaEnabled` already says so nothing is asked (a 404 on every visit was a failed request).
// A state that cannot be read still leads to the settings, without saying on or off.
import { StatusPill } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { ApiError, createAllauthClient, useLiveClient } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { onMounted, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

const SETTINGS = '/2fa';

const router = useRouter();
const config = useLiveClient().config;
const auth = createAllauthClient(config);
/** `on`/`off` once read; `unknown` when it could not be; `unavailable`: 2FA is off on the server. */
const state = shallowRef<'loading' | 'on' | 'off' | 'unknown' | 'unavailable'>(config.mfaEnabled === false ? 'unavailable' : 'loading');

onMounted(async () => {
  if (state.value === 'unavailable') return;
  try {
    const authenticators = await auth.authenticators();
    state.value = authenticators.some((item) => item.type === 'totp') ? 'on' : 'off';
  } catch (error) {
    state.value = error instanceof ApiError && error.status === 404 ? 'unavailable' : 'unknown';
  }
});
</script>

<template>
  <div
    v-if="state !== 'unavailable'"
    class="card-row"
    data-testid="two-factor"
  >
    <div class="card-row__text">
      <h3 class="card-row__title">
        {{ $t('accounts.account.security.twoFactor') }}
        <StatusPill
          v-if="state === 'on' || state === 'off'"
          data-testid="two-factor-state"
          size="sm"
          :tone="state === 'on' ? 'success' : 'neutral'"
          :label="state === 'on' ? $t('accounts.twoFactor.on') : $t('accounts.twoFactor.off')"
        />
      </h3>
      <p class="card-text">
        {{ state === 'off' ? $t('accounts.account.security.twoFactorOff') : $t('accounts.account.security.twoFactorOn') }}
      </p>
    </div>
    <ion-button
      data-testid="two-factor-manage"
      fill="outline"
      :disabled="state === 'loading'"
      @click="router.push(SETTINGS)"
    >
      <HubIcon
        slot="start"
        name="lucide:shield-check"
        aria-hidden="true"
      />
      {{ state === 'off' ? $t('accounts.account.security.setUp') : $t('accounts.account.security.manage') }}
    </ion-button>
  </div>
</template>

<style scoped src="./account-card.css"></style>
