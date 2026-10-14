<script setup lang="ts">
// Account → Profile (mockups `account.html` «profile»): the live `accounts.profile.get` — a skeleton while it
// loads, its failure with «Retry» (also when no answer comes in time: never a skeleton for ever, audit
// 2026-10-14 R-08), then «Your details» (ProfileForm) and the danger card, «Delete your account»
// (DeleteAccountCard), shown on every surface (PLAN-SAAS §3.6 point 6: Google Play asks for it in the apps).
import { useLive } from '@erplora/ui/sdk';
import { IonCard, IonCardContent, IonSkeletonText } from '@ionic/vue';
import { computed } from 'vue';

import LoadFailed from '../../../frontend/LoadFailed.vue';
import { useLiveState } from '../../../frontend/live-state';
import DeleteAccountCard from './DeleteAccountCard.vue';
import ProfileForm from './ProfileForm.vue';

const live = useLive('accounts.profile.get');
const state = useLiveState(live);
const profile = computed(() => live.data.value);
</script>

<template>
  <div class="tab-stack">
    <LoadFailed
      v-if="state.failed.value"
      testid="profile-error"
      retry-testid="profile-retry"
      :heading="$t('accounts.account.profile.loadError')"
      @retry="state.retry()"
    />

    <ion-card
      v-else-if="!profile"
      data-testid="profile-loading"
      :aria-label="$t('accounts.account.loading')"
    >
      <ion-card-content class="ion-padding">
        <ion-skeleton-text
          animated
          style="width: 30%; height: 16px"
        />
        <ion-skeleton-text
          animated
          style="width: 40px; height: 40px; border-radius: 50%; margin-top: 16px"
        />
        <ion-skeleton-text
          animated
          style="width: 100%; height: 52px; margin-top: 16px"
        />
        <ion-skeleton-text
          animated
          style="width: 100%; height: 52px; margin-top: 12px"
        />
      </ion-card-content>
    </ion-card>

    <template v-else>
      <ProfileForm :profile="profile" />
      <DeleteAccountCard :profile="profile" />
    </template>
  </div>
</template>

<style scoped>
.tab-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
