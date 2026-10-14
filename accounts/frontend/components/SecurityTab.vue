<script setup lang="ts">
// Account → Security (mockups `account.html` «security»): the card «Sign-in» with a row each for the password
// (PasswordRow), two-step verification (TwoFactorRow) and Google (ConnectedAccountsRow), from the live
// `accounts.profile.get` (whether the account has a password); then the active sessions (SessionsTable), which
// load on their own and take the height the card leaves (a nested `.panel-fill` of the page).
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSkeletonText } from '@ionic/vue';
import { computed } from 'vue';

import ConnectedAccountsRow from './ConnectedAccountsRow.vue';
import PasswordRow from './PasswordRow.vue';
import SessionsTable from './SessionsTable.vue';
import TwoFactorRow from './TwoFactorRow.vue';

const live = useLive('accounts.profile.get');
const profile = computed(() => live.data.value);
</script>

<template>
  <div class="tab-stack panel-fill">
    <InlineFeedback
      v-if="live.status.value === 'error' && !profile"
      tone="danger"
      data-testid="security-error"
      :heading="$t('accounts.account.profile.loadError')"
    >
      {{ $t('accounts.account.loadErrorBody') }}
      <template #actions>
        <ion-button
          data-testid="security-retry"
          size="small"
          fill="outline"
          @click="live.refresh()"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
          />
          {{ $t('accounts.account.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

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
