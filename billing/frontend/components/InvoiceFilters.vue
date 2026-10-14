<script setup lang="ts">
// The filters of Billing → Invoices in one control of the table's toolbar (Ioan, 2026-10-14: a clean SaaS, the
// toolbar on one line at 1440 px and two on a phone): a «Filters» button that counts the ones on, and a popover
// with the business (a popover select), the status (a segment: three visible options), the year (a popover
// select) and «Clear filters» while any is on. Nothing slides up from the bottom. It keeps no state: the page
// holds the filters (in the address) and hears `change` (`''` for «All») and `clear`. DataTable's own column
// filters paint a row under the toolbar and have no year: docs/UI-REQUESTS-panel.md asks for them in a popover.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonContent, IonLabel, IonPopover, IonSegment, IonSegmentButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import type { InvoicePaymentStatus } from '../../../frontend/sdk-types';

export type InvoiceFilterKey = 'business' | 'status' | 'year';

const props = defineProps<{
  /** The businesses whose invoices the account sees. */
  businesses: ReadonlyArray<{ id: string; name: string }>;
  /** The years offered, the newest first. */
  years: readonly number[];
  /** The filters on (`null` = all). */
  business: string | null;
  status: InvoicePaymentStatus | null;
  year: number | null;
}>();

const emit = defineEmits<{
  /** A filter chosen: its key and value (`''` = all). */
  change: [key: InvoiceFilterKey, value: string | number];
  /** «Clear filters». */
  clear: [];
}>();

/** The segment's value for «All»: a segment button needs a value of its own. */
const ALL = 'all';
const STATUSES: InvoicePaymentStatus[] = ['paid', 'open'];

const { t } = useI18n();
const open = shallowRef(false);
const event = shallowRef<Event>();

const active = computed(() => [props.business, props.status, props.year].filter((value) => value !== null && value !== '').length);

function show(trigger: Event): void {
  event.value = trigger;
  open.value = true;
}

function pick(key: InvoiceFilterKey, value: unknown): void {
  const chosen = value === undefined || value === null || value === ALL ? '' : (value as string | number);
  emit('change', key, chosen);
}
</script>

<template>
  <ion-button
    class="invoice-filters"
    data-testid="invoices-filters"
    size="small"
    fill="outline"
    aria-haspopup="dialog"
    :aria-expanded="open ? 'true' : 'false'"
    :aria-label="active ? t('billing.invoices.filters.buttonOn', { count: active }, active) : undefined"
    @click="show"
  >
    <HubIcon
      slot="start"
      class="invoice-filters__icon"
      name="ion:funnel"
      aria-hidden="true"
    />
    {{ $t('billing.invoices.filters.button') }}
    <span
      v-if="active"
      class="invoice-filters__count"
      data-testid="invoices-filters-count"
      aria-hidden="true"
    >{{ active }}</span>
  </ion-button>

  <ion-popover
    class="invoice-filters__popover"
    :is-open="open"
    :event="event"
    @did-dismiss="open = false"
  >
    <ion-content class="ion-padding">
      <div
        class="invoice-filters__panel"
        role="group"
        data-testid="invoices-filters-panel"
        :aria-label="$t('billing.invoices.filters.button')"
      >
        <ion-select
          data-testid="invoices-business"
          mode="md"
          fill="outline"
          label-placement="floating"
          interface="popover"
          :label="$t('billing.invoices.filters.business')"
          :value="business ?? ''"
          @ion-change="pick('business', $event.detail.value)"
        >
          <ion-select-option value="">
            {{ $t('billing.invoices.filters.allBusinesses') }}
          </ion-select-option>
          <ion-select-option
            v-for="item in businesses"
            :key="item.id"
            :value="item.id"
          >
            {{ item.name }}
          </ion-select-option>
        </ion-select>

        <div class="invoice-filters__field">
          <span
            id="invoice-filters-status"
            class="invoice-filters__label"
            data-testid="invoices-status-label"
          >{{ $t('billing.invoices.filters.status') }}</span>
          <ion-segment
            data-testid="invoices-status"
            aria-labelledby="invoice-filters-status"
            :value="status ?? ALL"
            @ion-change="pick('status', $event.detail.value)"
          >
            <ion-segment-button :value="ALL">
              <ion-label>{{ $t('billing.invoices.filters.all') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button
              v-for="value in STATUSES"
              :key="value"
              :value="value"
            >
              <ion-label>{{ $t(`billing.invoices.filters.${value}`) }}</ion-label>
            </ion-segment-button>
          </ion-segment>
        </div>

        <ion-select
          data-testid="invoices-year"
          mode="md"
          fill="outline"
          label-placement="floating"
          interface="popover"
          :label="$t('billing.invoices.filters.year')"
          :value="year ?? ''"
          @ion-change="pick('year', $event.detail.value)"
        >
          <ion-select-option value="">
            {{ $t('billing.invoices.filters.allYears') }}
          </ion-select-option>
          <ion-select-option
            v-for="value in years"
            :key="value"
            :value="value"
          >
            {{ value }}
          </ion-select-option>
        </ion-select>

        <ion-button
          v-if="active"
          class="invoice-filters__clear"
          data-testid="invoices-filters-clear"
          size="small"
          fill="clear"
          @click="emit('clear')"
        >
          <HubIcon
            slot="start"
            name="ion:close-outline"
            aria-hidden="true"
          />
          {{ $t('billing.invoices.filters.clear') }}
        </ion-button>
      </div>
    </ion-content>
  </ion-popover>
</template>

<style scoped>
/* As tall as the toolbar's other controls (DataTable's 36–38 px); 44 px to tap on a phone or a touch screen
   (audit 2026-10-14, R-13). */
.invoice-filters {
  min-height: 36px;
  margin: 0;
  text-transform: none;
  --border-radius: 10px;
}
@media (max-width: 640px), (pointer: coarse) {
  .invoice-filters {
    min-height: 44px;
  }
}
.invoice-filters__icon {
  margin-inline-end: 0.4em;
}
.invoice-filters__count {
  display: inline-grid;
  place-items: center;
  min-width: 1.25rem;
  height: 1.25rem;
  margin-inline-start: 0.4rem;
  padding: 0 0.3rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--ion-color-primary-contrast);
  background: var(--ion-color-primary);
}
.invoice-filters__popover {
  --width: min(22rem, calc(100vw - 2rem));
}
.invoice-filters__panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.invoice-filters__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
/* Each status as wide as its words: the `ios` segment's equal thirds (`grid-auto-columns: 1fr`) cut «Not
   collected» in a phone's popover. */
.invoice-filters__field ion-segment {
  grid-auto-columns: auto;
}
.invoice-filters__label {
  font-size: 0.8rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.invoice-filters__clear {
  align-self: flex-start;
  margin: 0;
  text-transform: none;
}
</style>
