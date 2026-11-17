<script setup lang="ts">
// Billing (`/dashboard/billing/:tab`): what the account pays ERPlora for its businesses, three sections in the
// footer tabbar, each at its own address. It is not selling, so it shows on every surface; paying, changing the
// card and changing or cancelling a plan are web only, inside each section. One payment at a time on the page
// (`providePaying`).
import { AppPage, HubIcon, type ShellTab } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { BILLING } from '../../../accounts/frontend/paths';
import BillingNotices from '../components/BillingNotices.vue';
import InvoicesTab from '../components/InvoicesTab.vue';
import PaymentTab from '../components/PaymentTab.vue';
import SubscriptionsTab from '../components/SubscriptionsTab.vue';
import { providePaying } from '../pay';

type Tab = 'invoices' | 'subscriptions' | 'payment';

const props = defineProps<{
  /** The section on screen (the route's `:tab`). */
  tab: Tab;
}>();

const SECTIONS: Array<{ id: Tab; icon: string }> = [
  { id: 'invoices', icon: 'ion:receipt-outline' },
  { id: 'subscriptions', icon: 'ion:sync-outline' },
  { id: 'payment', icon: 'ion:card-outline' },
];

const { t } = useI18n();
providePaying();

/** Invoices and Subscriptions are lists: they fill the page between the topbar and the tabbar. */
const fills = computed(() => props.tab !== 'payment');

const tabs = computed<ShellTab[]>(() =>
  SECTIONS.map((section) => ({ id: section.id, label: t(`billing.page.tabs.${section.id}`), icon: section.icon, to: `${BILLING}/${section.id}` })),
);
</script>

<template>
  <AppPage
    :title="$t('billing.page.title')"
    :content-layout="fills ? 'detail-fill' : 'detail'"
    :tabs="tabs"
    :tabs-label="$t('billing.page.tabsLabel')"
  >
    <div
      class="billing-stack"
      :class="{ 'panel-fill': fills }"
    >
      <p
        v-if="tab === 'invoices'"
        class="billing-lead"
        data-testid="billing-lead"
      >
        <HubIcon
          class="billing-lead__icon"
          name="ion:information-circle-outline"
          aria-hidden="true"
        />
        <span>{{ $t('billing.page.lead') }}</span>
      </p>
      <BillingNotices :tab="tab" />
      <InvoicesTab v-if="tab === 'invoices'" />
      <SubscriptionsTab v-else-if="tab === 'subscriptions'" />
      <PaymentTab v-else />
    </div>
  </AppPage>
</template>

<style scoped>
.billing-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.billing-lead {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 0;
  font-size: 0.9rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.billing-lead__icon {
  flex: none;
  margin-top: 2px;
  font-size: 15px;
}
</style>
