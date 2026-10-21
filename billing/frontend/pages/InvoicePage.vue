<script setup lang="ts">
// The page of one ERPlora invoice (`/billing/invoices/:id`; BILLING-G05, the old «Detalle de factura», and the
// «View» of `/dashboard/billing/invoices/`, BILLING-G92): `billing.invoice.get`, live, so «Issuing» turns into
// its fiscal status while it is on screen. Back returns to Invoices. A reading page (`detail`):
//   - its number (Stripe's reference while it is not collected), date, business, status and fiscal status;
//   - what it charges, line by line (the period, «Prorated», net, VAT and total), and the totals;
//   - who it is made out to, as on the day it was issued (a later change of the billing details never moves it);
//   - a credit note: its VeriFactu type and reason, and the invoice it rectifies, one tap away;
//   - «Download PDF» once the platform hub issued it, «Pay» (web only) while it is not collected.
// The server decides who sees it (its payer that day and the business's current owner): anybody else gets the
// server's 404, said as «could not load» with «Retry», as any failure.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { AppPage, HubIcon, toastError, toastInfo, WebOnly } from '@erplora/ui/shell';
import { type ApiError, useLive } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSkeletonText } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { RouterLink } from 'vue-router';

import { useLiveState } from '../../../frontend/live-state';
import LoadFailed from '../../../frontend/LoadFailed.vue';
import type { InvoiceDetailOut, InvoiceLineOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../../../hubs/frontend/error-text';
import { browser, operationUrl } from '../browser';
import PayInvoiceButton from '../components/PayInvoiceButton.vue';
import { formatDate } from '../format';
import { formatAmount, invoicePill } from '../invoices';
import { providePaying } from '../pay';

const props = defineProps<{
  /** The invoice (`Invoice.id`): the route's `:id`. */
  id: string;
}>();

const { t, locale } = useI18n();
const { text } = useErrorText();
providePaying();

const live = useLive('billing.invoice.get', () => ({ id: props.id }));
const load = useLiveState(live);
const invoice = computed<InvoiceDetailOut | undefined>(() => live.data.value ?? undefined);
const loadFailed = computed(() => load.failed.value && !invoice.value);

const title = computed(() => {
  const now = invoice.value;
  if (!now) return t('billing.invoicePage.title');
  if (!now.number) return t('billing.invoicePage.unnumbered', { reference: now.reference });
  return now.kind === 'credit_note'
    ? t('billing.invoicePage.creditNote', { number: now.number })
    : t('billing.invoicePage.invoice', { number: now.number });
});
const pill = computed(() => (invoice.value ? invoicePill(invoice.value, locale.value) : null));

const money = (cents: number) => formatAmount(cents, invoice.value?.currency ?? 'eur', locale.value);
const percent = (rate: string) => `${new Intl.NumberFormat(locale.value, { maximumFractionDigits: 2 }).format(Number(rate))}%`;

function period(line: InvoiceLineOut): string {
  if (!line.period_start || !line.period_end) return '';
  return t('billing.invoicePage.period', { start: formatDate(line.period_start, locale.value), end: formatDate(line.period_end, locale.value) });
}

const rectification = computed(() => {
  const r = invoice.value?.rectification;
  if (!r) return '';
  return r.reason ? t('billing.invoices.rectification', { type: r.type, reason: r.reason }) : t('billing.invoices.rectificationNoReason', { type: r.type });
});

const recipient = computed(() => {
  const to = invoice.value?.recipient;
  if (!to) return null;
  const place = [to.postal_code, to.city].filter(Boolean).join(' ');
  const country = to.country ? (new Intl.DisplayNames([locale.value], { type: 'region' }).of(to.country) ?? to.country) : '';
  return { ...to, address: [to.address, place].filter(Boolean).join(', '), country };
});

// ── The PDF: the platform hub's, asked when it is downloaded (README «Facturas de ERPlora») ─────────────
const fetching = shallowRef(false);

async function downloadPdf(): Promise<void> {
  const now = invoice.value;
  if (!now || fetching.value) return;
  fetching.value = true;
  try {
    await browser.download(operationUrl('billing.invoice.pdf', { id: now.id }), 'application/pdf');
  } catch (error) {
    const failure = error as ApiError;
    if (failure.code === 'billing.invoice_not_issued') void toastInfo(t('billing.invoices.pdfIssuing'));
    else if (failure.code === 'billing.platform_unavailable') void toastError(t('billing.invoices.pdfUnavailable'));
    else {
      console.error('billing: the invoice PDF could not be downloaded', error);
      void toastError(text(failure));
    }
  } finally {
    fetching.value = false;
  }
}
</script>

<template>
  <AppPage
    :title="title"
    back-href="/billing/invoices"
    content-layout="detail"
  >
    <div class="invoice-stack">
      <LoadFailed
        v-if="loadFailed"
        :heading="$t('billing.invoicePage.loadError')"
        :error="load.error.value"
        testid="invoice-error"
        retry-testid="invoice-retry"
        @retry="load.retry()"
      />

      <ion-card
        v-else-if="!invoice"
        data-testid="invoice-loading"
      >
        <ion-card-content class="ion-padding">
          <ion-skeleton-text
            animated
            style="width: 40%; height: 20px"
          />
          <ion-skeleton-text
            animated
            style="width: 70%; height: 14px"
          />
          <ion-skeleton-text
            animated
            style="width: 100%; height: 80px"
          />
        </ion-card-content>
      </ion-card>

      <template v-else>
        <ion-card data-testid="invoice-summary">
          <ion-card-content class="ion-padding invoice-head">
            <div class="invoice-head__title">
              <h2
                class="invoice-title"
                data-testid="invoice-title"
              >
                {{ title }}
              </h2>
              <StatusPill
                v-if="pill"
                :tone="pill.tone"
                :label="pill.label"
                :busy="pill.busy"
              />
            </div>
            <dl class="invoice-facts">
              <div>
                <dt>{{ $t('billing.invoicePage.date') }}</dt>
                <dd>{{ formatDate(invoice.date, locale) }}</dd>
              </div>
              <div>
                <dt>{{ $t('billing.invoicePage.business') }}</dt>
                <dd>{{ invoice.business.name }}</dd>
              </div>
              <div>
                <dt>{{ $t('billing.invoicePage.payment') }}</dt>
                <dd>{{ invoice.payment_status_label }}</dd>
              </div>
              <div>
                <dt>{{ $t('billing.invoicePage.fiscal') }}</dt>
                <dd>{{ invoice.fiscal_status_label }}</dd>
              </div>
            </dl>
            <InlineFeedback
              v-if="invoice.rectification"
              tone="info"
              icon="ion:information-circle-outline"
              data-testid="invoice-rectification"
              :heading="rectification"
            >
              <RouterLink
                v-if="invoice.rectifies"
                :to="`/billing/invoices/${invoice.rectifies.id}`"
                data-testid="invoice-rectifies"
              >
                {{ $t('billing.invoices.rectifies', { number: invoice.rectifies.number }) }}
              </RouterLink>
            </InlineFeedback>
            <div class="invoice-actions">
              <ion-button
                v-if="invoice.can.pdf"
                fill="outline"
                :disabled="fetching"
                data-testid="invoice-pdf"
                @click="downloadPdf"
              >
                <HubIcon
                  slot="start"
                  name="ion:download-outline"
                  aria-hidden="true"
                />
                {{ $t('billing.invoices.pdf') }}
              </ion-button>
              <WebOnly v-if="invoice.can.pay || invoice.actions.includes('pay')">
                <PayInvoiceButton :invoice="invoice" />
              </WebOnly>
            </div>
          </ion-card-content>
        </ion-card>

        <ion-card>
          <ion-card-content class="ion-padding">
            <h2 class="invoice-section">
              {{ $t('billing.invoicePage.lines') }}
            </h2>
            <ul class="invoice-lines">
              <li
                v-for="line in invoice.lines"
                :key="line.position"
                class="invoice-line"
                data-testid="invoice-line"
              >
                <div class="invoice-line__main">
                  <span class="invoice-line__desc">{{ line.description }}</span>
                  <span class="invoice-line__total">{{ money(line.total_cents) }}</span>
                </div>
                <p class="invoice-line__meta">
                  <span v-if="period(line)">{{ period(line) }}</span>
                  <span v-if="line.proration">{{ $t('billing.invoicePage.prorated') }}</span>
                  <span>{{ $t('billing.invoicePage.lineAmounts', { net: money(line.net_cents), rate: percent(line.tax_rate), tax: money(line.tax_cents) }) }}</span>
                </p>
              </li>
            </ul>
            <dl
              class="invoice-totals"
              data-testid="invoice-totals"
            >
              <div>
                <dt>{{ $t('billing.invoicePage.net') }}</dt>
                <dd>{{ money(invoice.net_cents) }}</dd>
              </div>
              <div>
                <dt>{{ $t('billing.invoicePage.vat') }}</dt>
                <dd>{{ money(invoice.tax_cents) }}</dd>
              </div>
              <div class="invoice-totals__total">
                <dt>{{ $t('billing.invoicePage.total') }}</dt>
                <dd>{{ money(invoice.total_cents) }}</dd>
              </div>
            </dl>
          </ion-card-content>
        </ion-card>

        <ion-card
          v-if="recipient"
          data-testid="invoice-recipient"
        >
          <ion-card-content class="ion-padding">
            <h2 class="invoice-section">
              {{ $t('billing.invoicePage.recipient') }}
            </h2>
            <p class="invoice-recipient">
              <strong>{{ recipient.name }}</strong>
              <span v-if="recipient.tax_id">{{ recipient.tax_id }}</span>
              <span v-if="recipient.address">{{ recipient.address }}</span>
              <span v-if="recipient.country">{{ recipient.country }}</span>
              <span v-if="recipient.email">{{ recipient.email }}</span>
            </p>
          </ion-card-content>
        </ion-card>
      </template>
    </div>
  </AppPage>
</template>

<style scoped>
.invoice-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.invoice-stack ion-card {
  margin: 0;
}
.invoice-head {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.invoice-head__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}
.invoice-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--ion-text-color);
  overflow-wrap: anywhere;
}
.invoice-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 10px 16px;
  margin: 0;
}
.invoice-facts dt,
.invoice-totals dt {
  font-size: 0.8rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.invoice-facts dd {
  margin: 2px 0 0;
  color: var(--ion-text-color);
  overflow-wrap: anywhere;
}
.invoice-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.invoice-actions ion-button {
  margin: 0;
}
.invoice-section {
  margin: 0 0 8px;
  font-size: 1rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.invoice-lines {
  list-style: none;
  margin: 0;
  padding: 0;
}
.invoice-line {
  padding: 10px 0;
  border-bottom: 1px solid var(--ep-border, color-mix(in oklab, var(--ion-text-color) 12%, transparent));
}
.invoice-line__main {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--ion-text-color);
}
.invoice-line__desc {
  min-width: 0;
  overflow-wrap: anywhere;
}
.invoice-line__total {
  flex: none;
  font-variant-numeric: tabular-nums;
}
.invoice-line__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
  margin: 4px 0 0;
  font-size: 0.82rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.invoice-totals {
  display: grid;
  gap: 6px;
  margin: 12px 0 0 auto;
  max-width: 20rem;
}
.invoice-totals div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}
.invoice-totals dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  color: var(--ion-text-color);
}
.invoice-totals__total dt,
.invoice-totals__total dd {
  font-size: 1rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.invoice-recipient {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  color: var(--ion-text-color);
  overflow-wrap: anywhere;
}
</style>
