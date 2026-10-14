<script setup lang="ts">
// What waits for a payment, on top of every tab of Billing (mockups `billing.html`; README §6.18): on
// Invoices one banner per invoice not collected (UnpaidInvoiceNotice); on Subscriptions and Payment details
// the same warning in one line with a link to it (or to all of them). It also says «Invoice paid» when one
// is paid (`unpaid.ts`). Nothing here sells: it shows on every surface, and the banners say off the web
// how to pay.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatAmount } from '../invoices';
import { useUnpaidInvoices } from '../unpaid';
import UnpaidInvoiceNotice from './UnpaidInvoiceNotice.vue';

const props = defineProps<{
  tab: 'invoices' | 'subscriptions' | 'payment';
}>();

const { t, locale } = useI18n();
const { items } = useUnpaidInvoices();

/** The one-line warning off Invoices: what is owed and where to see it. */
const line = computed(() => {
  const owed = items.value;
  if (props.tab === 'invoices' || owed.length === 0) return null;
  const first = owed[0].invoice;
  const amount = formatAmount(
    owed.reduce((sum, item) => sum + item.invoice.total_cents, 0),
    first.currency,
    locale.value,
  );
  if (owed.length === 1) {
    return {
      text: t('billing.notice.lineOne', { name: first.business.name, amount }),
      link: t('billing.notice.viewOne'),
      to: { path: '/billing/invoices', query: first.business.id ? { business: first.business.id, status: 'open' } : { status: 'open' } },
    };
  }
  return {
    text: t('billing.notice.lineMany', { count: owed.length, amount }),
    link: t('billing.notice.viewMany'),
    to: { path: '/billing/invoices', query: { status: 'open' } },
  };
});
</script>

<template>
  <template v-if="tab === 'invoices'">
    <UnpaidInvoiceNotice
      v-for="item in items"
      :key="item.invoice.id"
      :invoice="item.invoice"
      :business="item.business"
      :data-testid="`billing-unpaid-${item.invoice.id}`"
    />
  </template>
  <p
    v-else-if="line"
    class="billing-alert"
    role="alert"
    data-testid="billing-unpaid-line"
  >
    <HubIcon
      class="billing-alert__icon"
      name="lucide:credit-card"
    />
    <span data-testid="billing-unpaid-text">{{ line.text }}</span>
    <router-link
      class="billing-alert__link"
      :to="line.to"
    >
      {{ line.link }}
    </router-link>
  </p>
</template>

<style scoped>
.billing-alert {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  margin: 0;
  padding: 10px 14px;
  border-inline-start: 4px solid var(--ep-danger, var(--ion-color-danger));
  border-radius: var(--ep-radius, 8px);
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--ep-danger-text, var(--ion-color-danger));
  background: var(--ep-danger-tint, color-mix(in srgb, var(--ion-color-danger) 10%, transparent));
}
.billing-alert__icon {
  flex: none;
  font-size: 16px;
}
.billing-alert__link {
  margin-inline-start: auto;
  font-weight: 600;
  color: inherit;
  white-space: nowrap;
}
</style>
