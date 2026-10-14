<script setup lang="ts">
// Account → Security (mockups `account.html` «security»): the card «Sign-in» with a row each for the password
// (PasswordRow), two-step verification (TwoFactorRow) and Google (ConnectedAccountsRow), from the live
// `accounts.profile.get` (whether the account has a password); then the active sessions (SessionsTable), which
// load on their own and take the height the card leaves (a nested `.panel-fill` of the page). The account's
// failure is said with «Retry», also when no answer comes in time: never a skeleton for ever (audit 2026-10-14 R-08).
import { useLive } from '@erplora/ui/sdk';
import { IonCard, IonCardContent, IonSkeletonText } from '@ionic/vue';
import { computed } from 'vue';

import LoadFailed from '../../../frontend/LoadFailed.vue';
import { useLiveState } from '../../../frontend/live-state';
import ConnectedAccountsRow from './ConnectedAccountsRow.vue';
import PasswordRow from './PasswordRow.vue';
import SessionsTable from './SessionsTable.vue';
import TwoFactorRow from './TwoFactorRow.vue';

const live = useLive('accounts.profile.get');
const state = useLiveState(live);
const profile = computed(() => live.data.value);
</script>

<template>
  <div class="tab-stack panel-fill">
    <LoadFailed
      v-if="state.failed.value"
      testid="security-error"
      retry-testid="security-retry"
      :heading="$t('accounts.account.profile.loadError')"
      @retry="state.retry()"
    />

    <ion-card
      v-else-if="!profile"
      data-testid="security-loading"
      :aria-label="$t('accounts.account.loading')"
    >
      <ion-card-content class="ion-padding">
        <ion-skeleton-text
          animated
          style="width: 20%; height: 16px"
        />
        <ion-skeleton-text
          animated
          style="width: 100%; height: 48px; margin-top: 16px"
        />
        <ion-skeleton-text
          animated
          style="width: 100%; height: 48px; margin-top: 12px"
        />
      </ion-card-content>
    </ion-card>

    <ion-card
      v-else
      data-testid="sign-in-card"
    >
      <ion-card-content class="ion-padding">
        <h2 class="card-title">
          {{ $t('accounts.account.security.heading') }}
        </h2>
        <div class="sign-in-rows">
          <PasswordRow
            :has-password="profile.has_password"
            :email="profile.email"
          />
          <TwoFactorRow />
          <ConnectedAccountsRow :has-password="profile.has_password" />
        </div>
      </ion-card-content>
    </ion-card>

    <SessionsTable />
  </div>
</template>

<style scoped src="./account-card.css"></style>
<style scoped>
.tab-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sign-in-rows {
  margin-top: 4px;
}
</style>
