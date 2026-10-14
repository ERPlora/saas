<script setup lang="ts">
// The notice of an unpaid invoice of a business (mockups `businesses.html`, `business.html` «past-due»;
// README §4 and §6.18; PLAN-SAAS §3.3): since when it is unpaid and, while it still works, until when
// (7 days of grace from the invoice, `unpaidDeadline`), as days (never the minute, audit R-15); suspended,
// that it waits for the payment and nothing is deleted. On the web, «Pay the invoice» goes to Stripe's page
// (`pay_url`, only for whoever may pay it); after a declined card «Change card» (Stripe's Customer Portal) is
// the way out and «Pay» waits for it (`UnpaidActions`, audit R-09). Inside the apps, how to settle it, without
// a button nor a link (README §4).
import { InlineFeedback } from '@erplora/ui/components';
import { WebOnly } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatDate } from '../../../billing/frontend/format';
import type { BusinessRowOut } from '../../../frontend/sdk-types';
import { unpaidDeadline } from '../business-status';
import UnpaidActions from './UnpaidActions.vue';

const props = defineProps<{
  business: Pick<BusinessRowOut, 'id' | 'name' | 'status' | 'unpaid_reason' | 'unpaid_since' | 'pay_url'>;
}>();

const { t, locale } = useI18n();

const suspended = computed(() => props.business.status === 'suspended');
const body = computed(() => {
  const since = props.business.unpaid_since;
  if (!since) return suspended.value ? t('hubs.list.unpaid.suspendedBody') : t('hubs.list.unpaid.pastDueBody');
  const date = formatDate(since, locale.value);
  if (suspended.value) return t('hubs.unpaid.suspendedSince', { since: date });
  return t('hubs.unpaid.pastDueSince', { since: date, until: formatDate(unpaidDeadline(since), locale.value) });
});
const declined = computed(() => props.business.unpaid_reason === 'card_declined');
</script>

<template>
  <InlineFeedback
    tone="danger"
    icon="ion:card-outline"
    :heading="
      suspended
        ? $t('hubs.list.unpaid.suspendedHeading', { name: business.name })
        : $t('hubs.list.unpaid.pastDueHeading', { name: business.name })
    "
  >
    <span data-testid="unpaid-body">{{ body }}</span>
    <WebOnly>
      <span
        v-if="business.pay_url && declined"
        class="unpaid-card"
        data-testid="unpaid-card"
      >{{ $t('hubs.unpaid.cardDeclined') }}</span>
      <template #app>
        <span
          class="unpaid-app"
          data-testid="unpaid-app"
        >{{ $t('hubs.unpaid.app') }}</span>
      </template>
    </WebOnly>
    <template
      v-if="business.pay_url"
      #actions
    >
      <UnpaidActions :business="business" />
    </template>
  </InlineFeedback>
</template>

<style scoped>
.unpaid-card,
.unpaid-app {
  display: block;
  margin-top: 4px;
}
</style>
