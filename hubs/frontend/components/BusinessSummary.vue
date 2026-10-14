<script setup lang="ts">
// The Summary of a business (mockups `business.html` «summary», PLAN-SAAS §3.6): four cards.
//   - Plan: its name, the trial while it lasts, the devices it covers (from `hubs.plan.list`: the plans
//     on sale, public) and the people (`seats`, the server's count against the plan's cap). Changing
//     or cancelling the plan is the Store's (web only); inside the apps it says where, without a link.
//   - Usage: the people on the business against the places of the plan (UsageMeter + UsageCounter).
//   - «On your devices» (DeviceAccessCard) and the business's details.
// Deleted, only the plan (cancelled with the deletion) and the details are left.
import { formatDateTime, UsageCounter, UsageMeter } from '@erplora/ui/components';
import { WebOnly } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { IonCard, IonCardContent } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessDetailOut, PlanOut } from '../../../frontend/sdk-types';
import { countryName } from '../regions';
import DeviceAccessCard from './DeviceAccessCard.vue';

const props = defineProps<{
  business: BusinessDetailOut;
}>();

const { t, locale } = useI18n();
const client = useLiveClient();
const plans = shallowRef<PlanOut[]>([]);

onMounted(async () => {
  try {
    plans.value = (await client.api.call('hubs.plan.list')).plans;
  } catch {
    // Without the plans on sale the devices read «—»: the rest of the card is the business's.
  }
});

const deleted = computed(() => props.business.status === 'deleting');
/** What the business uses now: the plan it tries while the trial lasts, else its own. */
const effective = computed(() => props.business.trial_plan ?? props.business.plan);
const devices = computed(() => {
  const plan = plans.value.find((candidate) => candidate.slug === effective.value?.slug);
  if (!plan) return '—';
  return plan.max_devices ? String(plan.max_devices) : t('hubs.common.unlimited');
});
const seats = computed(() => props.business.seats);
const users = computed(() =>
  seats.value.limit === null ? t('hubs.common.unlimited') : t('hubs.business.plan.usersOf', { used: seats.value.used, limit: seats.value.limit }),
);
</script>

<template>
  <div class="card-grid">
    <ion-card data-testid="summary-plan">
      <ion-card-content class="ion-padding">
        <div class="page-eyebrow">
          {{ $t('hubs.business.plan.eyebrow') }}
        </div>
        <h2 class="card-title">
          {{ business.plan?.name ?? $t('hubs.business.plan.none') }}
        </h2>
        <p
          v-if="deleted"
          class="card-text"
        >
          {{ $t('hubs.business.plan.deleted') }}
        </p>
        <template v-else>
          <p
            v-if="business.trial_plan && business.trial_end"
            class="card-text"
            data-testid="summary-trial"
          >
            {{ $t('hubs.business.plan.trial', { plan: business.trial_plan.name, date: formatDateTime(business.trial_end, locale) }) }}
          </p>
          <dl class="kv">
            <div>
              <dt>{{ $t('hubs.business.plan.devices') }}</dt>
              <dd>{{ devices }}</dd>
            </div>
            <div>
              <dt>{{ $t('hubs.business.plan.users') }}</dt>
              <dd>{{ users }}</dd>
            </div>
          </dl>
          <WebOnly>
            <template #app>
              <p class="card-text">
                {{ $t('hubs.common.storeInBrowser') }}
              </p>
            </template>
          </WebOnly>
        </template>
      </ion-card-content>
    </ion-card>

    <ion-card
      v-if="!deleted"
      data-testid="summary-usage"
    >
      <ion-card-content class="ion-padding">
        <div class="page-eyebrow">
          {{ $t('hubs.business.usage.eyebrow') }}
        </div>
        <h2 class="card-title">
          {{ $t('hubs.business.usage.title') }}
        </h2>
        <UsageMeter
          v-if="seats.limit !== null"
          class="ion-margin-top"
          :label="$t('hubs.business.usage.meter')"
          :value="seats.used"
          :max="seats.limit"
          :hint="$t('hubs.business.usage.meterHint')"
        />
        <div class="mini-kpis">
          <UsageCounter
            :label="$t('hubs.business.usage.people')"
            :value="seats.used"
          />
          <UsageCounter
            :label="$t('hubs.business.usage.covered')"
            :value="seats.limit ?? $t('hubs.common.unlimited')"
          />
        </div>
        <p
          v-if="seats.limit === null"
          class="card-text small"
        >
          {{ $t('hubs.business.usage.hint') }}
        </p>
      </ion-card-content>
    </ion-card>

    <DeviceAccessCard
      v-if="!deleted"
      :host="business.host"
    />

    <ion-card data-testid="summary-facts">
      <ion-card-content class="ion-padding">
        <div class="page-eyebrow">
          {{ $t('hubs.business.facts.eyebrow') }}
        </div>
        <h2 class="card-title">
          {{ $t('hubs.business.facts.title') }}
        </h2>
        <dl class="kv">
          <div>
            <dt>{{ $t('hubs.business.facts.type') }}</dt>
            <dd>{{ business.business_type?.name ?? $t('hubs.business.facts.noType') }}</dd>
          </div>
          <div>
            <dt>{{ $t('hubs.business.facts.country') }}</dt>
            <dd>{{ countryName(business.country, locale) }}</dd>
          </div>
          <div>
            <dt>{{ $t('hubs.business.facts.members') }}</dt>
            <dd>{{ seats.used }}</dd>
          </div>
          <div>
            <dt>{{ $t('hubs.business.facts.created') }}</dt>
            <dd>{{ formatDateTime(business.created_at, locale) }}</dd>
          </div>
        </dl>
      </ion-card-content>
    </ion-card>
  </div>
</template>

<style scoped src="./panel-card.css"></style>
<style scoped>
/* Two columns from 720 px (mockups' `.card-grid.cols-2`). */
.card-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(0, 1fr);
}
@media (min-width: 720px) {
  .card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.mini-kpis {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}
</style>
