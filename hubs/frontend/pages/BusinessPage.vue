<script setup lang="ts">
// A business's page (`/dashboard/businesses/:id/:tab`, round 17 §2.3; mockups `business.html`): the live
// `hubs.business.get` (owner and admins; anybody else gets the server's 403/404 as an error), a header
// with the business's name, address, status, plan and role and «Open» (solid on the Summary, outlined
// elsewhere, V-23; gone while suspended or deleted), and four sections in the footer tabbar, each at
// its own address: Summary · Members · Modules · Settings. Deleted, a banner says until when it can be
// recovered (the owner recovers it there); a payment pending or a suspension is said under the header.
// The Summary of a Spanish business ends with the authorisation for ERPlora to file its invoices (fiscal's
// RepresentationCard), whose «Manage in your business» opens the business as «Open» does.
// Modules: turning apps on and off is the Hub's (PLAN §20.4), so the tab says so and the header's «Open»,
// solid there as on the Summary, is its one action (no second «Open» in the card: Ioan, 2026-10-14).
// Members fills the page between the topbar and the tabbar (`detail-fill` + `.panel-fill`). Its states are
// truthful (`useLiveState`, audit 2026-10-14 R-08): no answer in time is an error with «Retry», never a skeleton
// for ever; an error or a deleted business has no tabbar (W-18, W-B3: its sections would only repeat it), and a
// deleted one shows its Summary whatever the address. Members only needs the business's id (the address's), so
// it mounts with the page and its list goes in the page's first `/api/live` stream with `hubs.business.get`; it
// shows once the business is there. Waiting for the business to mount it made the SDK reopen the stream, and the
// first request ended aborted (FIX-SAAS-BUSINESSES-LIVE-DOUBLE-OPEN). The Summary's authorisation card goes the same
// way: it asks with the page and shows only for a Spanish business that lives (`files`); hidden otherwise, so the
// business's answer never takes a subscription out of the stream.
import { formatDateTime, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { AppPage, HubIcon, type ShellTab, toastError, toastSuccess, useSurface, WebOnly } from '@erplora/ui/shell';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSkeletonText, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { BUSINESSES } from '../../../accounts/frontend/paths';
import RepresentationCard from '../../../fiscal/frontend/components/RepresentationCard.vue';
import { useLiveState } from '../../../frontend/live-state';
import LoadFailed from '../../../frontend/LoadFailed.vue';
import { reasonKey, statusPill } from '../business-status';
import BusinessSettings from '../components/BusinessSettings.vue';
import BusinessSummary from '../components/BusinessSummary.vue';
import DangerZone from '../components/DangerZone.vue';
import HostName from '../components/HostName.vue';
import MembersTab from '../components/MembersTab.vue';
import UnpaidNotice from '../components/UnpaidNotice.vue';
import { useErrorText } from '../error-text';
import { useOpenBusiness } from '../open-business';

type Tab = 'summary' | 'members' | 'modules' | 'settings';

const props = defineProps<{
  /** The business (`Hub.id`). */
  id: string;
  /** The section on screen. */
  tab: Tab;
}>();

const SECTIONS: Array<{ id: Tab; icon: string }> = [
  { id: 'summary', icon: 'ion:grid-outline' },
  { id: 'members', icon: 'ion:people-outline' },
  { id: 'modules', icon: 'ion:apps-outline' },
  { id: 'settings', icon: 'ion:settings-outline' },
];

const { t, locale } = useI18n();
const { inApp } = useSurface();
const live = useLive('hubs.business.get', () => ({ id: props.id }));
const { open, opening } = useOpenBusiness();
const restore = useCommand('hubs.business.restore');
const { text } = useErrorText();

const load = useLiveState(live);

const business = computed(() => live.data.value);
/** The business could not be loaded: the page says why, with nothing else (no tabbar, no section). */
const loadFailed = computed(() => load.failed.value && !business.value);
const deleted = computed(() => business.value?.status === 'deleting');
/** No tabbar on an error or a deleted business: every section would only repeat it. */
const tabs = computed<ShellTab[]>(() =>
  deleted.value || loadFailed.value ? [] : SECTIONS.map((section) => ({
    id: section.id,
    label: t(`hubs.business.tabs.${section.id}`),
    icon: section.icon,
    to: `${BUSINESSES}/${props.id}/${section.id}`,
  })),
);
/** The section on screen: a deleted business only has its Summary (with the way to recover it). */
const section = computed<Tab>(() => (deleted.value ? 'summary' : props.tab));
/** Members is a list: it fills the page between the topbar and the tabbar (Ioan, 2026-10-14). */
const fills = computed(() => section.value === 'members');
const opensAtAll = computed(() => !!business.value && business.value.status !== 'suspended' && !deleted.value);
/** The authorisation for ERPlora to file its invoices with the AEAT (VeriFactu): a Spanish business's, while it lives. */
const files = computed(() => business.value?.country === 'ES' && !deleted.value);
const state = computed(() => {
  const now = business.value;
  if (!now || deleted.value) return '';
  const key = reasonKey(now, inApp.value);
  // Only the launcher opens a business by itself when it is ready: here it says it will be soon.
  if (key === 'hubs.reason.preparing') return t('hubs.reason.preparingSoon');
  return key ? t(key) : '';
});
const meta = computed(() => {
  const now = business.value;
  if (!now) return '';
  return now.plan ? `${t('hubs.common.plan', { name: now.plan.name })} · ${now.role_label}` : now.role_label;
});

async function recover(): Promise<void> {
  try {
    const recovered = await restore.run({ id: props.id });
    void toastSuccess(t('hubs.list.restored', { name: recovered.name }));
  } catch {
    void toastError(text(restore.error.value));
  }
}
</script>

<template>
  <AppPage
    :title="business?.name ?? $t('hubs.list.title')"
    :back-href="BUSINESSES"
    :content-layout="fills ? 'detail-fill' : 'detail'"
    :tabs="tabs"
    :tabs-label="$t('hubs.business.tabsLabel')"
  >
    <div
      class="page-stack"
      :class="{ 'panel-fill': fills }"
    >
      <LoadFailed
        v-if="loadFailed"
        :heading="$t('hubs.business.loadError')"
        :message="$t('hubs.business.loadErrorBody')"
        :error="load.error.value"
        :forbidden-heading="$t('hubs.business.forbidden')"
        testid="business-error"
        retry-testid="business-retry"
        @retry="load.retry()"
      />

      <div
        v-else-if="!business"
        class="page-stack"
        data-testid="business-loading"
      >
        <div class="biz-header ion-padding">
          <ion-skeleton-text
            animated
            class="skeleton-tile"
          />
          <div class="skeleton-lines">
            <ion-skeleton-text
              animated
              style="width: 40%; height: 18px"
            />
            <ion-skeleton-text
              animated
              style="width: 60%; height: 12px"
            />
          </div>
        </div>
        <ion-card>
          <ion-card-content class="ion-padding">
            <ion-skeleton-text
              animated
              style="width: 30%; height: 12px"
            />
            <ion-skeleton-text
              animated
              style="width: 100%; height: 60px"
            />
          </ion-card-content>
        </ion-card>
      </div>

      <template v-else>
        <InlineFeedback
          v-if="deleted"
          tone="danger"
          icon="ion:trash-outline"
          data-testid="business-deleted"
          :heading="$t('hubs.business.deleting.heading', { date: formatDateTime(business.purge_after, locale) })"
        >
          {{
            business.can.restore
              ? $t('hubs.business.deleting.body', { date: formatDateTime(business.deletion_requested_at, locale) })
              : $t('hubs.business.deleting.bodyNotOwner', { date: formatDateTime(business.deletion_requested_at, locale) })
          }}
          <template
            v-if="business.can.restore"
            #actions
          >
            <ion-button
              data-testid="business-restore"
              size="small"
              :disabled="restore.pending.value"
              @click="recover"
            >
              <ion-spinner
                v-if="restore.pending.value"
                slot="start"
                name="crescent"
                aria-hidden="true"
              />
              <HubIcon
                v-else
                slot="start"
                name="ion:refresh-outline"
                aria-hidden="true"
              />
              {{ $t('hubs.danger.restore') }}
            </ion-button>
          </template>
        </InlineFeedback>

        <div
          class="biz-header ion-padding"
          :class="{ 'is-compact': section !== 'summary' }"
          data-testid="business-header"
        >
          <div class="biz-header__main">
            <span class="tile-icon"><HubIcon
              name="ion:storefront-outline"
              aria-hidden="true"
            /></span>
            <div class="biz-header__text">
              <p class="biz-header__title">
                {{ business.name }}
              </p>
              <p class="biz-header__url">
                <HostName :host="business.host" />
              </p>
              <div class="biz-header__pills">
                <StatusPill v-bind="statusPill(business, t, locale)" />
                <span class="biz-header__meta">{{ meta }}</span>
              </div>
            </div>
          </div>
          <div
            v-if="opensAtAll"
            class="biz-header__actions"
          >
            <ion-button
              data-testid="business-open"
              :fill="section === 'summary' || section === 'modules' ? 'solid' : 'outline'"
              :disabled="!business.can.open || !!opening"
              :aria-label="$t('hubs.common.openName', { name: business.name })"
              @click="open(business)"
            >
              <ion-spinner
                v-if="opening"
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

        <UnpaidNotice
          v-if="business.status === 'past_due' || business.status === 'suspended'"
          :business="business"
          data-testid="business-unpaid"
        />
        <p
          v-else-if="state"
          class="business-state"
          :class="{ 'is-danger': statusPill(business, t, locale).tone === 'danger' }"
          data-testid="business-state"
        >
          {{ state }}
        </p>

        <template v-if="section === 'summary'">
          <BusinessSummary :business="business" />
        </template>
        <ion-card
          v-else-if="section === 'modules'"
          data-testid="business-modules"
        >
          <ion-card-content class="ion-padding modules-card">
            <span class="tile-icon"><HubIcon
              name="ion:apps-outline"
              aria-hidden="true"
            /></span>
            <div class="modules-card__text">
              <h2 class="card-title">
                {{ $t('hubs.business.modules.heading') }}
              </h2>
              <p class="card-text">
                {{ $t('hubs.business.modules.body') }}
              </p>
              <WebOnly>
                <template #app>
                  <p class="card-text">
                    {{ $t('hubs.common.storeInBrowser') }}
                  </p>
                </template>
              </WebOnly>
            </div>
          </ion-card-content>
        </ion-card>
        <template v-else-if="section === 'settings'">
          <BusinessSettings :business="business" />
          <DangerZone :business="business" />
        </template>
      </template>

      <RepresentationCard
        v-if="section === 'summary' && !loadFailed"
        v-show="files"
        :id="id"
        :can-manage="opensAtAll && !!business?.can.open"
        :managing="!!opening"
        @manage="business && open(business)"
      />
      <MembersTab
        v-if="section === 'members' && !loadFailed"
        :id="id"
        :business="business"
      />
    </div>
  </AppPage>
</template>

<style scoped src="../components/buttons.css"></style>
<style scoped src="../components/panel-card.css"></style>
<style scoped>
.page-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
/* The business's header (mockups' `.biz-header`): a tinted band with the tile, the name and «Open». */
.biz-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px 16px;
  border: 1px solid var(--ion-border-color);
  border-radius: var(--ep-radius, 14px);
  background: color-mix(in oklab, var(--ion-color-primary) 5%, var(--ion-card-background, #fff));
}
.biz-header__main {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1 1 260px;
  min-width: 0;
}
.biz-header__text {
  min-width: 0;
}
.biz-header__title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.biz-header__url {
  margin: 2px 0 0;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
  overflow-wrap: anywhere;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.biz-header__pills {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.biz-header__meta {
  font-size: 0.82rem;
  color: color-mix(in oklab, var(--ion-text-color) 68%, transparent);
}
.biz-header__actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}
/* Outside the Summary the header is compact: the name and its status (mockups, V-23). */
.biz-header.is-compact {
  flex-wrap: nowrap;
}
.biz-header.is-compact .biz-header__url,
.biz-header.is-compact .biz-header__meta,
.biz-header.is-compact .tile-icon {
  display: none;
}
.biz-header.is-compact .biz-header__pills {
  margin-top: 2px;
}
@media (max-width: 599px) {
  .biz-header:not(.is-compact) .biz-header__actions,
  .biz-header:not(.is-compact) .biz-header__actions ion-button {
    flex: 1 1 auto;
    width: 100%;
  }
}
.tile-icon {
  display: inline-grid;
  place-items: center;
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  font-size: 22px;
  color: var(--ion-color-primary);
  background: color-mix(in oklab, var(--ion-color-primary) 12%, transparent);
}
.business-state {
  margin: -4px 2px 0;
  font-size: 0.88rem;
  line-height: 1.45;
  color: var(--ep-warning-on-tint, color-mix(in oklch, var(--ion-color-warning) 55%, var(--ion-text-color)));
}
.business-state.is-danger {
  color: var(--ep-danger-on-tint, var(--ion-color-danger));
}
.modules-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.modules-card__text {
  min-width: 0;
}
.skeleton-tile {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  margin: 0;
}
.skeleton-lines {
  flex: 1;
}
</style>
