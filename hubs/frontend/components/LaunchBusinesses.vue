<script setup lang="ts">
// The account's businesses on the entry (`/launch`): one is a card with «Open X», disabled while it is prepared and
// gone while suspended, with why it does not open; several are a list in the server's order (the last opened first)
// with «Open» on each. The page holds the opening: «Open» is handed back to it, and it says which one is opening.
// A business that owes an invoice says its real deadline and, on the web for whoever may pay it, «Pay the
// invoice» (or «Change card») is the main action, «Open» the second, outlined. A deleted business offers its
// owner «Recover business» there, within its 90 days.
import { StatusPill } from '@erplora/ui/components';
import { HubIcon, useSurface } from '@erplora/ui/shell';
import { IonButton, IonProgressBar, IonSpinner } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

import type { BusinessRowOut } from '../../../frontend/sdk-types/hubs';
import { reasonDate, reasonKey, statusPill } from '../business-status';
import HostName from './HostName.vue';
import RecoverButton from './RecoverButton.vue';
import UnpaidActions from './UnpaidActions.vue';

const props = defineProps<{ rows: BusinessRowOut[]; opening: string | null }>();
const emit = defineEmits<{ open: [business: BusinessRowOut] }>();

const { t, locale } = useI18n();
const { inApp, isWeb } = useSurface();

// ── What each business says ───────────────────────────────────────────────────────────────────
const pill = (business: BusinessRowOut) => statusPill(business, t, locale.value);

function reason(business: BusinessRowOut, short = false): string {
  const key = reasonKey(business, inApp.value);
  if (!key) return '';
  // With several nothing opens by itself: the neutral «ready in a few seconds».
  if (short && key === 'hubs.reason.preparing') return t('hubs.reason.preparingSoon');
  return t(key, { date: reasonDate(business, locale.value) });
}

/** On the web, whoever may pay a business's unpaid invoice is offered to pay it first. */
const owes = (business: BusinessRowOut) =>
  isWeb.value && !!business.pay_url && (business.status === 'past_due' || business.status === 'suspended');

function meta(business: BusinessRowOut, withPlan: boolean): string {
  return withPlan && business.plan
    ? `${t('hubs.common.plan', { name: business.plan.name })} · ${business.role_label}`
    : business.role_label;
}

/** Suspended or deleted: «Open» is not offered at all. */
const opensAtAll = (business: BusinessRowOut) => business.status !== 'suspended' && business.status !== 'deleting';
/** The name of «Open»: the business it opens, and «Opening …» while this page opens it. */
const openName = (business: BusinessRowOut) =>
  t(props.opening === business.id ? 'hubs.open.opening' : 'hubs.common.openName', { name: business.name });
</script>

<template>
  <template v-if="rows.length === 1 && rows[0]">
    <div
      class="launch-biz ion-padding"
      :class="{ 'is-waiting': rows[0].status === 'preparing' }"
      data-testid="launch-business"
    >
      <span class="biz-card__icon"><HubIcon
        name="ion:storefront-outline"
        aria-hidden="true"
      /></span>
      <div class="launch-biz__text">
        <h2>{{ rows[0].name }}</h2>
        <p class="mono launch-biz__url">
          <HostName :host="rows[0].host" />
        </p>
        <p class="launch-biz__pills">
          <StatusPill v-bind="pill(rows[0])" />
          <span class="launch-biz__meta">{{ meta(rows[0], true) }}</span>
        </p>
      </div>
    </div>
    <p
      v-if="reason(rows[0])"
      class="launch-reason"
      :class="{
        'is-warning': rows[0].status === 'past_due',
        'is-danger': rows[0].status === 'suspended' || rows[0].status === 'deleting' || pill(rows[0]).tone === 'danger',
      }"
      data-testid="launch-reason"
    >
      {{ reason(rows[0]) }}
    </p>
    <ion-progress-bar
      v-if="rows[0].status === 'preparing' && pill(rows[0]).tone !== 'danger'"
      type="indeterminate"
      class="launch-progress"
      :aria-label="$t('hubs.preparing.progress')"
    />
    <UnpaidActions
      v-if="owes(rows[0])"
      :business="rows[0]"
      size="large"
      expand="block"
      class="launch-main"
    />
    <RecoverButton
      v-if="rows[0].status === 'deleting'"
      :business="rows[0]"
      size="large"
      expand="block"
      class="launch-main"
    />
    <ion-button
      v-if="opensAtAll(rows[0])"
      data-testid="launch-open"
      expand="block"
      :size="owes(rows[0]) ? undefined : 'large'"
      :fill="owes(rows[0]) ? 'outline' : 'solid'"
      :class="owes(rows[0]) ? 'launch-second' : 'launch-main'"
      :disabled="!rows[0].can_open || !!opening"
      @click="emit('open', rows[0])"
    >
      <ion-spinner
        v-if="opening === rows[0].id"
        slot="start"
        name="crescent"
        aria-hidden="true"
      />
      <HubIcon
        v-else
        slot="start"
        name="ion:log-in-outline"
        aria-hidden="true"
      />
      {{ openName(rows[0]) }}
    </ion-button>
  </template>

  <div
    v-else
    class="launch-list"
  >
    <div
      v-for="(business, index) in rows"
      :key="business.id"
      class="launch-biz ion-padding"
      :class="{ 'is-waiting': business.status === 'preparing' }"
      data-testid="launch-business"
    >
      <span class="biz-card__icon"><HubIcon
        name="ion:storefront-outline"
        aria-hidden="true"
      /></span>
      <div class="launch-biz__text">
        <h2>{{ business.name }}</h2>
        <p class="mono launch-biz__url">
          <HostName :host="business.host" />
        </p>
        <p class="launch-biz__pills">
          <StatusPill v-bind="pill(business)" />
          <span class="launch-biz__meta">{{ meta(business, false) }}</span>
          <StatusPill
            v-if="index === 0 && business.last_opened_at"
            class="tag-recent"
            tone="info"
            :dot="false"
            :label="$t('hubs.common.lastOpened')"
          />
        </p>
        <p
          v-if="reason(business, true)"
          class="launch-biz__why"
        >
          {{ reason(business, true) }}
        </p>
        <UnpaidActions
          v-if="owes(business)"
          :business="business"
          named
          size="small"
          class="launch-biz__pay"
        />
        <RecoverButton
          v-if="business.status === 'deleting'"
          :business="business"
          named
          size="small"
          class="launch-biz__pay"
        />
      </div>
      <ion-button
        v-if="opensAtAll(business)"
        data-testid="launch-open"
        :fill="owes(business) ? 'outline' : 'solid'"
        :aria-label="openName(business)"
        :disabled="!business.can_open || !!opening"
        @click="emit('open', business)"
      >
        <ion-spinner
          v-if="opening === business.id"
          slot="start"
          name="crescent"
          aria-hidden="true"
        />
        <HubIcon
          v-else
          slot="start"
          name="ion:log-in-outline"
          aria-hidden="true"
        />
        {{ $t('hubs.common.open') }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
.launch-main {
  margin-top: 16px;
}
.launch-second {
  margin-top: 10px;
}
.launch-biz__pay {
  margin-top: 8px;
}
.launch-list {
  display: grid;
  gap: 10px;
}
.launch-biz {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--ion-border-color);
  border-radius: 12px;
  min-width: 0;
}
.biz-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  font-size: 22px;
  color: var(--ion-color-primary);
  background: color-mix(in oklab, var(--ion-color-primary) 12%, transparent);
}
.launch-biz.is-waiting .biz-card__icon {
  color: var(--ion-color-medium);
  background: color-mix(in oklab, var(--ion-color-medium) 12%, transparent);
}
.launch-biz__text {
  flex: 1 1 auto;
  min-width: 0;
}
.launch-biz__text h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.3;
  color: var(--ion-text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.launch-biz__text p {
  margin: 3px 0 0;
  font-size: 0.78rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.mono {
  font-family: var(--font-mono, ui-monospace, monospace);
}
.launch-biz__url {
  overflow-wrap: anywhere;
}
.launch-biz__pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.launch-biz__meta {
  font-size: 0.82rem;
}
.launch-biz__text p.launch-biz__why {
  margin-top: 4px;
  font-size: 0.8rem;
  line-height: 1.35;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.launch-biz ion-button {
  flex: none;
  min-height: 44px;
}
.launch-reason {
  margin: 12px 2px 0;
  font-size: 0.88rem;
  line-height: 1.45;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.launch-reason.is-warning {
  color: var(--ep-warning-on-tint, color-mix(in oklch, var(--ion-color-warning) 55%, var(--ion-text-color)));
}
.launch-reason.is-danger {
  color: var(--ep-danger-on-tint, var(--ion-color-danger));
}
.launch-progress {
  margin-top: 10px;
  border-radius: 999px;
}
@media (max-width: 420px) {
  .launch-list .launch-biz > .biz-card__icon {
    display: none;
  }
}
</style>
