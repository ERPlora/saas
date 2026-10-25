<script setup lang="ts">
// The Summary of a business (mockups `business.html` «summary», PLAN-SAAS §3.6): four cards.
//   - Plan: its name, the trial while it lasts, the devices it covers and the apps it turns on at once
//     (`max_apps`, the cap the Hub applies since hub#256; from `hubs.plan.list`: the plans on sale, public)
//     and the people (`seats`, the server's count against the plan's cap). Changing
//     or cancelling the plan is the Store's (web only): whoever handles the billing gets «Upgrade plan» on
//     Free and «Change plan» on a paid one, to the Store with this business chosen (BILLING-F07); inside the
//     apps it says where, without a link.
//   - Usage: what the Hub measured last night (`business.usage`, PLAN-SAAS §5; lot L4-A): the storage of
//     its files as a percentage of the space of the plan (UsageMeter; never the bytes) and the people
//     active that day and in the 30 days up to it (UsageCounter); «yesterday» or the day measured. Before
//     the first night, that there is no data yet. The people against the places stay a line of the plan.
//   - «On your devices» (DeviceAccessCard) and the business's details.
// Deleted, only the plan (cancelled with the deletion) and the details are left.
import { formatDateTime, StatusPill, UsageCounter, UsageMeter } from '@erplora/ui/components';
import { WebOnly } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessDetailOut, PlanOut } from '../../../frontend/sdk-types';
import { countryName } from '../regions';
import { formatUsageDay, isYesterday } from '../usage-day';
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
/** The plan on sale the business uses now; none while the plans load or if they could not. */
const effectivePlan = computed(() => plans.value.find((candidate) => candidate.slug === effective.value?.slug));
const devices = computed(() => {
  const plan = effectivePlan.value;
  if (!plan) return '—';
  return plan.max_devices ? String(plan.max_devices) : t('hubs.common.unlimited');
});
/** How many apps the business may choose to turn on at once: 0 is no cap. */
const apps = computed(() => {
  const plan = effectivePlan.value;
  if (!plan) return '—';
  return plan.max_apps ? String(plan.max_apps) : t('hubs.business.plan.appsUnlimited');
});
/** Free is the plan without a price: from it the Store upgrades; from a paid one it changes. */
const onFree = computed(() => {
  const plan = plans.value.find((candidate) => candidate.slug === props.business.plan?.slug);
  return !props.business.plan || (!!plan && Number(plan.price_monthly) === 0 && Number(plan.price_annual) === 0);
});
const toStore = computed(() => `/store/plans?business=${encodeURIComponent(props.business.id)}`);
const seats = computed(() => props.business.seats);
const users = computed(() =>
  seats.value.limit === null ? t('hubs.common.unlimited') : t('hubs.business.plan.usersOf', { used: seats.value.used, limit: seats.value.limit }),
);

/** From this full the hint warns that the space runs out (the old quota's warning, 80 %). */
const STORAGE_WARNING_PERCENT = 80;
const usage = computed(() => props.business.usage);
const percent = computed(() => usage.value?.storage.percent ?? null);
const storageHint = computed(() => {
  const plan = effective.value?.name ?? '';
  if (percent.value !== null && percent.value >= 100) return t('hubs.business.usage.storageFull', { plan });
  if (percent.value !== null && percent.value >= STORAGE_WARNING_PERCENT) return t('hubs.business.usage.storageLow', { plan });
  return t('hubs.business.usage.storageHint');
});
const measuredYesterday = computed(() => (usage.value ? isYesterday(usage.value.day) : false));
const measuredDay = computed(() => (usage.value ? formatUsageDay(usage.value.day, locale.value) : ''));
const activeLabel = computed(() =>
  measuredYesterday.value ? t('hubs.business.usage.activeYesterday') : t('hubs.business.usage.activeOn', { date: measuredDay.value }),
);
const dayHint = computed(() =>
  measuredYesterday.value ? t('hubs.business.usage.fromYesterday') : t('hubs.business.usage.fromDay', { date: measuredDay.value }),
);
</script>

<template>
  <div class="card-grid">
    <ion-card data-testid="summary-plan">
      <ion-card-content class="ion-padding">
        <div class="page-eyebrow">
          {{ $t('hubs.business.plan.eyebrow') }}
        </div>
        <div class="plan-title">
          <h2 class="card-title">
            {{ business.plan?.name ?? $t('hubs.business.plan.none') }}
          </h2>
          <StatusPill
            v-if="business.is_payer"
            tone="info"
            :dot="false"
            :label="$t('hubs.unpaid.payer')"
            data-testid="summary-payer"
          />
        </div>
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
            <div data-testid="summary-plan-apps">
              <dt>{{ $t('hubs.business.plan.apps') }}</dt>
              <dd>{{ apps }}</dd>
            </div>
            <div>
              <dt>{{ $t('hubs.business.plan.users') }}</dt>
              <dd>{{ users }}</dd>
            </div>
          </dl>
          <WebOnly>
            <ion-button
              v-if="business.can.manage_billing"
              :router-link="toStore"
              fill="outline"
              size="small"
              class="plan-store"
              data-testid="summary-plan-store"
            >
              {{ onFree ? $t('hubs.business.plan.upgrade') : $t('hubs.business.plan.change') }}
            </ion-button>
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
        <template v-if="usage">
          <UsageMeter
            v-if="percent !== null"
            class="ion-margin-top"
            :label="$t('hubs.business.usage.storage')"
            :percent="percent"
            :hint="storageHint"
          />
          <div class="mini-kpis">
            <UsageCounter
              :label="activeLabel"
              :value="usage.active_users.on_day"
            />
            <UsageCounter
              :label="$t('hubs.business.usage.last30')"
              :value="usage.active_users.last_30_days"
            />
          </div>
          <p
            class="card-text small"
            data-testid="summary-usage-day"
          >
            {{ dayHint }}
          </p>
        </template>
        <p
          v-else
          class="card-text"
          data-testid="summary-usage-empty"
        >
          {{ $t('hubs.business.usage.empty') }}
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
/* «Upgrade plan» / «Change plan», under what the plan covers. */
.plan-store {
  margin: 12px 0 0;
}
.plan-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.mini-kpis {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}
</style>
