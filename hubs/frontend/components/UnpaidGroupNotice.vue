<script setup lang="ts">
// Several businesses with an unpaid invoice (audit 2026-10-14, R-15; mockups `businesses.html`, «2 negocios
// tienen facturas sin pagar»): ONE notice instead of one per business, so two of them no longer take half the
// page. The suspended first; each line says its business and its date (the day, never the minute: since when it
// is suspended, or when it will be) and, on the web, its own way to pay (`UnpaidActions`: «Pay the invoice», or
// «Change card» after a declined card). Inside the apps, where to pay, without a button (README §4).
import { InlineFeedback } from '@erplora/ui/components';
import { WebOnly } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatDate } from '../../../billing/frontend/format';
import type { BusinessRowOut } from '../../../frontend/sdk-types';
import { unpaidDeadline } from '../business-status';
import UnpaidActions from './UnpaidActions.vue';

type Unpaid = Pick<BusinessRowOut, 'id' | 'name' | 'status' | 'unpaid_reason' | 'unpaid_since' | 'pay_url'>;

const props = defineProps<{
  businesses: Unpaid[];
}>();

const { t, locale } = useI18n();

/** The suspended first, then the ones about to be; the server's order otherwise. */
const ordered = computed(() =>
  [...props.businesses].sort((a, b) => Number(b.status === 'suspended') - Number(a.status === 'suspended')),
);

function sentence(business: Unpaid): string {
  const since = business.unpaid_since;
  let text: string;
  if (business.status === 'suspended') {
    text = since
      ? t('hubs.list.unpaid.lineSuspendedSince', { name: business.name, date: formatDate(since, locale.value) })
      : t('hubs.list.unpaid.lineSuspended', { name: business.name });
  } else {
    const until = formatDate(unpaidDeadline(since), locale.value);
    text = until
      ? t('hubs.list.unpaid.linePastDueUntil', { name: business.name, date: until })
      : t('hubs.list.unpaid.linePastDue', { name: business.name });
  }
  return business.unpaid_reason === 'card_declined' ? `${text} ${t('hubs.list.unpaid.lineDeclined')}` : text;
}
</script>

<template>
  <InlineFeedback
    tone="danger"
    icon="ion:card-outline"
    :heading="$t('hubs.list.unpaid.groupHeading', { count: businesses.length })"
  >
    <ul class="unpaid-lines">
      <li
        v-for="business in ordered"
        :key="business.id"
        class="unpaid-line"
        data-testid="businesses-unpaid-line"
      >
        <span class="unpaid-line__text">{{ sentence(business) }}</span>
        <UnpaidActions
          :business="business"
          named
          size="small"
        />
      </li>
    </ul>
    <span class="unpaid-foot">{{ $t('hubs.list.unpaid.nothingDeleted') }}</span>
    <WebOnly>
      <template #app>
        <span
          class="unpaid-foot"
          data-testid="unpaid-app"
        >{{ $t('hubs.unpaid.app') }}</span>
      </template>
    </WebOnly>
  </InlineFeedback>
</template>

<style scoped>
.unpaid-lines {
  display: grid;
  gap: 8px;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}
.unpaid-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 12px;
}
.unpaid-line__text {
  flex: 1 1 18rem;
  min-width: 0;
}
.unpaid-foot {
  display: block;
  margin-top: 6px;
}
</style>
