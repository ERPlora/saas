<script setup lang="ts">
// What waits for a payment, on top of every tab of Billing (mockups `billing.html`; README §6.18): on
// Invoices the banner of the invoice not collected (UnpaidInvoiceNotice), or ONE banner for two or more
// (UnpaidGroupNotice; mockups «past-due-two», audit 2026-10-14 R-15); on Subscriptions and Payment details
// the same warning in one line with a link to it (or to all of them). It also says «Invoice paid» when one
// is paid (`unpaid.ts`). Nothing here sells: it shows on every surface, and the banners say off the web
// how to pay. When the unpaid invoices could not be checked (audit 2026-10-14, R-04), off Invoices it says so
// with «Retry» instead of keeping quiet; on Invoices the list itself shows them and says when it fails.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatAmount } from '../invoices';
import { useUnpaidInvoices } from '../unpaid';
import UnpaidGroupNotice from './UnpaidGroupNotice.vue';
import UnpaidInvoiceNotice from './UnpaidInvoiceNotice.vue';

const props = defineProps<{
  tab: 'invoices' | 'subscriptions' | 'payment';
}>();

const { t, locale } = useI18n();
const { items, state } = useUnpaidInvoices();

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
    <UnpaidGroupNotice
      v-if="items.length > 1"
      :items="items"
      data-testid="billing-unpaid-group"
    />
    <UnpaidInvoiceNotice
      v-else-if="items.length === 1"
      :invoice="items[0].invoice"
      :business="items[0].business"
      :data-testid="`billing-unpaid-${items[0].invoice.id}`"
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
      aria-hidden="true"
    />
    <span data-testid="billing-unpaid-text">{{ line.text }}</span>
    <router-link
      class="billing-alert__link"
      :to="line.to"
    >
      {{ line.link }}
    </router-link>
  </p>
  <p
    v-else-if="state.failed.value"
    class="billing-alert billing-alert--unknown"
    role="status"
    data-testid="billing-unpaid-unknown"
  >
    <HubIcon
      class="billing-alert__icon"
      name="ion:alert-circle-outline"
      aria-hidden="true"
    />
    <span data-testid="billing-unpaid-unknown-text">{{ $t('billing.notice.unknown') }}</span>
    <ion-button
      class="billing-alert__retry"
      size="small"
      fill="clear"
      data-testid="billing-unpaid-retry"
      @click="state.retry()"
    >
      <HubIcon
        slot="start"
        name="ion:refresh-outline"
        aria-hidden="true"
      />
      {{ $t('billing.notice.retry') }}
    </ion-button>
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
.billing-alert--unknown {
  border-inline-start-color: var(--ep-warning, var(--ion-color-warning));
  color: var(--ep-warning-text, var(--ion-text-color));
  background: var(--ep-warning-tint, color-mix(in srgb, var(--ion-color-warning) 12%, transparent));
}
.billing-alert__retry {
  margin: 0 0 0 auto;
  text-transform: none;
}
@media (max-width: 640px) {
  .billing-alert__retry {
    min-height: 44px;
  }
}
.billing-alert__link {
  margin-inline-start: auto;
  font-weight: 600;
  color: inherit;
  white-space: nowrap;
}
/* A real tap target on a phone or a touch screen (audit 2 R-13: «View the invoices» measured 104×22). */
@media (max-width: 640px), (pointer: coarse) {
  .billing-alert__link {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
  }
}
</style>
