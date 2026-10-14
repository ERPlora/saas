<script setup lang="ts">
// Billing → Invoices (mockups `billing.html`; README §3b, §4 and §6.18; UX-AUDIT-4 W-F9, W-F15, V-34, X-18):
// ERPlora's invoices of every business the account owns or pays, live (`billing.invoice.list`), in a
// server-side DataTable that turns into cards up to 1100 px:
//   - invoice (our number; Stripe's reference until it is paid; under a credit note, «Credit note» and the
//     invoice it rectifies, which finds it; with its VeriFactu type and reason, «Credit note R1 · reason»), date,
//     business, amount and status («Not collected», «Issuing» until the platform hub issues it, «Paid»);
//   - filters by business — also `?business=` (an unknown one shows every invoice, saying so) —, status and
//     year, kept in the address (Subscriptions links here with them), in ONE «Filters» control of the toolbar
//     (InvoiceFilters: a popover; Ioan 2026-10-14, the toolbar on one line at 1440 px); a search by number;
//   - the list fills the page between the topbar and the tabbar (`fill`, a `.panel-fill` stack); rows per page
//     only past the shortest page (README §3b);
//   - per row, «Pay» (fixed and labelled; web only; disabled while it waits for another card) and the PDF
//     once issued; a selection with «Download PDF (n)», which says the ones still being issued;
//   - «Download Excel»: the CSV of everything the filters show, for the accountant. The toolbar stays on one
//     line from 641 px (audit 2026-10-14, R-14): when the button falls to a second line it folds to its icon
//     (named by its label) and the search narrows (`toolbar-fit.ts`); on a phone it reads «Excel».
// Files are asked for and saved only when the answer is the file (`browser.ts`; audit 2026-10-14, R-05): one
// still being issued (404) says so and its PDF waits, the invoice service down (503) says it, and nothing is
// ever saved as `pdf.json`. Empty, it says why (Free charges nothing); failing, it says it could not load.
import { DataTable, type DataTableAction, type DataTableActionEvent, type DataTableColumn, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { HubIcon, toastError, toastInfo, useSurface, WebOnly } from '@erplora/ui/shell';
import { type ApiError, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { type ComponentPublicInstance, computed, shallowRef, useTemplateRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import { useLiveState } from '../../../frontend/live-state';
import { useErrorText } from '../../../hubs/frontend/error-text';
import type { InvoiceFilterIn, InvoicePaymentStatus, InvoiceRowOut } from '../../../frontend/sdk-types';
import { browser, operationUrl } from '../browser';
import { formatDate } from '../format';
import { formatAmount, invoiceBusinesses, invoiceName, invoicePill, yearOptions } from '../invoices';
import { usePayInvoice } from '../pay';
import { useToolbarFit } from '../toolbar-fit';
import InvoiceFilters from './InvoiceFilters.vue';

const PAGE_SIZES = [10, 25, 50];
/** README §3b: the invoices' list is wide; cards up to 1100 px. */
const CARD_BREAKPOINT = 1100;
const STATUSES: InvoicePaymentStatus[] = ['paid', 'open'];

const { t, locale } = useI18n();
const route = useRoute();
const router = useRouter();
const { text } = useErrorText();
const { isWeb } = useSurface();
const { pay, paying } = usePayInvoice();
const client = useLiveClient();

// ── The filters, in the address ─────────────────────────────────────────────────────────────────
const businessList = useLive('hubs.business.list', { limit: 100 });
const options = computed(() => invoiceBusinesses(businessList.data.value?.rows ?? [], locale.value));

const asked = computed(() => (typeof route.query.business === 'string' && route.query.business) || null);
const unknownBusiness = computed(() => !!asked.value && !!businessList.data.value && !options.value.some((row) => row.id === asked.value));
const hubId = computed(() => (unknownBusiness.value ? null : asked.value));
const status = computed(() => {
  const value = route.query.status;
  return typeof value === 'string' && (STATUSES as string[]).includes(value) ? (value as InvoicePaymentStatus) : null;
});
const year = computed(() => {
  const value = Number(route.query.year);
  return Number.isInteger(value) && value >= 2000 ? value : null;
});
const years = yearOptions();

const search = shallowRef('');
const page = shallowRef(0);
const pageSize = shallowRef(25);
/** Pages the live window holds: 1 on a desk; each «Load more» on a phone adds one. */
const windowPages = shallowRef(1);

function goToPage(n: number): void {
  page.value = n;
  windowPages.value = 1;
}

const query = computed({
  get: () => search.value,
  set: (value: string) => {
    search.value = value;
    goToPage(0);
  },
});

function setPageSize(size: number): void {
  pageSize.value = size;
  goToPage(0);
}

/** A filter in the address (`''` drops it): the list starts again from its first page. */
function setFilter(key: 'business' | 'status' | 'year', value: unknown): void {
  const next = { ...route.query };
  if (value === '' || value === null || value === undefined) delete next[key];
  else next[key] = String(value);
  void router.replace({ path: route.path, query: next });
}

/** «Clear filters»: business, status and year go; the search stays (it is the table's own box). */
function clearFilters(): void {
  const next = { ...route.query };
  delete next.business;
  delete next.status;
  delete next.year;
  void router.replace({ path: route.path, query: next });
}

function showAll(): void {
  const next = { ...route.query };
  delete next.business;
  delete next.status;
  delete next.year;
  search.value = '';
  void router.replace({ path: route.path, query: next });
}

const filters = computed<InvoiceFilterIn>(() => ({
  ...(hubId.value ? { hub_id: hubId.value } : {}),
  ...(status.value ? { status: status.value } : {}),
  ...(year.value ? { year: year.value } : {}),
  ...(search.value.trim() ? { search: search.value.trim() } : {}),
}));
const filtered = computed(() => Object.keys(filters.value).length > 0);

// Other filters, other invoices: from the first page, nothing selected.
watch(
  () => [hubId.value, status.value, year.value],
  () => {
    goToPage(0);
    selected.value = [];
  },
);

// ── The list ────────────────────────────────────────────────────────────────────────────────────
const live = useLive('billing.invoice.list', () => ({
  ...filters.value,
  limit: pageSize.value * windowPages.value,
  offset: page.value * pageSize.value,
}));
const rows = computed<InvoiceRowOut[]>(() => live.data.value?.rows ?? []);
/** Loading, failed (the query, the stream, or nothing in time) or a real answer: never «No invoices yet» on a
 *  failure (audit 2026-10-14, R-04). The businesses only feed the filter: their failure blocks nothing. */
const state = useLiveState(live, { isEmpty: (data) => data.total === 0 });
const loadError = computed(() => (state.failed.value ? text(state.error.value) || t('billing.load.reason') : undefined));

// A page emptied elsewhere steps back to the last page that still has rows.
watch(live.data, (now) => {
  if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
    goToPage(Math.ceil(now.total / pageSize.value) - 1);
  }
});

const columns = computed(() => [
  { key: 'number', label: t('billing.invoices.columns.number'), cell: 'number', width: 'minmax(8.5rem,1.2fr)', priority: 'high' },
  {
    key: 'date',
    label: t('billing.invoices.columns.date'),
    width: 'minmax(6rem,1fr)',
    format: (_: unknown, row: InvoiceRowOut) => formatDate(row.date, locale.value, 'UTC'),
  },
  {
    key: 'business',
    label: t('billing.invoices.columns.business'),
    width: 'minmax(8rem,1.3fr)',
    format: (_: unknown, row: InvoiceRowOut) => row.business.name,
  },
  {
    key: 'total_cents',
    label: t('billing.invoices.columns.amount'),
    align: 'right',
    width: 'minmax(5.5rem,1fr)',
    format: (_: unknown, row: InvoiceRowOut) => formatAmount(row.total_cents, row.currency, locale.value),
  },
  { key: 'status', label: t('billing.invoices.columns.status'), cell: 'status', width: 'minmax(7.5rem,1fr)' },
] satisfies DataTableColumn<InvoiceRowOut>[]);

const labels = computed(() => ({ loadError: t('billing.invoices.loadError'), retry: t('billing.invoices.retry') }));
const entityLabel = (count: number) => t('billing.invoices.entity', count);

/** Per row, what the server says (`actions`): «Pay» stays when the others fold (README §3b). */
const actions = computed<DataTableAction<InvoiceRowOut>[]>(() => [
  {
    id: 'pay',
    label: t('billing.invoices.pay'),
    icon: 'ion:card-outline',
    color: 'primary',
    pinned: true,
    showLabel: true,
    hidden: (row) => !isWeb.value || !row.actions.includes('pay'),
    disabled: (row) => !row.can.pay || !!paying.value,
    loading: (row) => paying.value === row.id,
  },
  {
    id: 'pdf',
    label: t('billing.invoices.pdf'),
    icon: 'ion:download-outline',
    color: 'primary',
    hidden: (row) => !row.actions.includes('pdf'),
    disabled: (row) => notIssued.value.has(row.id),
    loading: (row) => fetching.value.has(row.id),
  },
]);

function onAction({ actionId, row }: DataTableActionEvent<InvoiceRowOut>): void {
  if (actionId === 'pay' && row.can.pay) void pay(row);
  else if (actionId === 'pdf') void downloadPdfs([row]);
}

// ── Credit notes ────────────────────────────────────────────────────────────────────────────────
/** What each credit note on screen rectifies (its number), asked once per credit note: the list does not
 *  carry it, its detail does (`billing.invoice.get`). */
const rectified = shallowRef(new Map<string, string>());
const lookedUp = new Set<string>();

async function lookUpRectified(id: string): Promise<void> {
  try {
    const detail = await client.api.call('billing.invoice.get', { id });
    if (detail.rectifies) rectified.value = new Map(rectified.value).set(id, detail.rectifies.number);
  } catch (error) {
    console.error('billing: what a credit note rectifies could not be read', error);
  }
}
watch(
  rows,
  (now) => {
    for (const row of now) {
      if (row.kind !== 'credit_note' || lookedUp.has(row.id)) continue;
      lookedUp.add(row.id);
      void lookUpRectified(row.id);
    }
  },
  { immediate: true },
);

/** What a credit note is: its VeriFactu type and reason («Credit note R1 · Duplicate charge»), or the server's
 *  word for it when it carries no type. */
function creditNoteLabel(row: InvoiceRowOut): string {
  const rectification = row.rectification;
  if (!rectification) return row.kind_label;
  return rectification.reason
    ? t('billing.invoices.rectification', { type: rectification.type, reason: rectification.reason })
    : t('billing.invoices.rectificationNoReason', { type: rectification.type });
}

/** The invoice a credit note rectifies, found by its number. */
function showRectified(number: string): void {
  query.value = number;
}

// ── Files ───────────────────────────────────────────────────────────────────────────────────────
/** The selection, kept across pages; each selected row as it was last seen. */
const selected = shallowRef<string[]>([]);
const seen = new Map<string, InvoiceRowOut>();
watch(rows, (now) => {
  for (const row of now) seen.set(row.id, row);
});

/** The invoices the server said are still being issued (404 `billing.invoice_not_issued`), with their row as it
 *  was then: their PDF waits, as «Issuing» does, until the list sends that row changed. */
const notIssued = shallowRef(new Map<string, string>());
watch(rows, (now) => {
  if (!notIssued.value.size) return;
  const next = new Map(notIssued.value);
  for (const row of now) if (next.get(row.id) !== undefined && next.get(row.id) !== JSON.stringify(row)) next.delete(row.id);
  if (next.size !== notIssued.value.size) notIssued.value = next;
});
/** The PDFs being asked for now. */
const fetching = shallowRef(new Set<string>());

function withId(set: ReadonlySet<string>, id: string, on: boolean): Set<string> {
  const next = new Set(set);
  if (on) next.add(id);
  else next.delete(id);
  return next;
}

/** What a failed file says; `null` for one still being issued (said apart). */
function fileError(error: ApiError): string | null {
  if (error.code === 'billing.invoice_not_issued') return null;
  if (error.code === 'billing.platform_unavailable') return t('billing.invoices.pdfUnavailable');
  return text(error);
}

/** Downloads the PDF of each issued one, one after the other; says once how many are still being issued
 *  (and once what failed, not per file). Alone, one still being issued says so in its own words. */
async function downloadPdfs(invoices: InvoiceRowOut[]): Promise<void> {
  let waiting = 0;
  let failure: string | null = null;
  for (const invoice of invoices) {
    if (!invoice.can.pdf || notIssued.value.has(invoice.id)) {
      waiting += 1;
      continue;
    }
    fetching.value = withId(fetching.value, invoice.id, true);
    try {
      await browser.download(operationUrl('billing.invoice.pdf', { id: invoice.id }), 'application/pdf');
    } catch (error) {
      const said = fileError(error as ApiError);
      if (said === null) {
        notIssued.value = new Map(notIssued.value).set(invoice.id, JSON.stringify(invoice));
        waiting += 1;
      } else {
        console.error('billing: an invoice PDF could not be downloaded', error);
        failure ??= said;
      }
    } finally {
      fetching.value = withId(fetching.value, invoice.id, false);
    }
  }
  if (failure) void toastError(failure);
  if (!waiting) return;
  const alone = invoices.length === 1;
  void toastInfo(alone ? t('billing.invoices.pdfIssuing') : t('billing.invoices.pdfNotReady', { count: waiting }, waiting));
}

function downloadSelected(): void {
  void downloadPdfs(selected.value.flatMap((id) => seen.get(id) ?? []));
}

// ── The toolbar on one line ─────────────────────────────────────────────────────────────────────
const csvButton = useTemplateRef<ComponentPublicInstance>('csvButton');
const fit = useToolbarFit(computed(() => (csvButton.value?.$el as Element | undefined) ?? null));
// «Download PDF (n)» comes and goes with the selection: the full toolbar may fit again, or not.
watch(
  () => selected.value.length > 0,
  () => fit.retry(),
);

async function downloadCsv(): Promise<void> {
  try {
    await browser.download(operationUrl('billing.invoice.csv', filters.value), 'text/csv');
  } catch (error) {
    console.error('billing: the invoices CSV could not be downloaded', error);
    void toastError(text(error as ApiError));
  }
}

// ── Empty ───────────────────────────────────────────────────────────────────────────────────────
/** Only a business on Free is filtered: it has no invoices, and says so (X-18). */
const freeBusiness = computed(() => {
  if (!hubId.value || status.value || year.value || search.value.trim()) return null;
  const row = options.value.find((business) => business.id === hubId.value);
  return row?.plan?.slug === 'free' ? row : null;
});
</script>

<template>
  <div :class="['invoices', 'panel-fill', { 'invoices--compact': fit.compact.value }]">
    <InlineFeedback
      v-if="unknownBusiness"
      tone="neutral"
      role="status"
      data-testid="invoices-unknown-business"
    >
      {{ $t('billing.invoices.unknownBusiness') }}
    </InlineFeedback>

    <DataTable
      v-model:search="query"
      v-model:selected="selected"
      testid="invoices"
      server-side
      searchable
      selectable
      fill
      :title="$t('billing.invoices.title')"
      :rows="rows"
      :total="live.data.value?.total ?? 0"
      :page="page"
      :page-size="pageSize"
      :page-size-options="PAGE_SIZES"
      :page-size-chooser="(live.data.value?.total ?? 0) > PAGE_SIZES[0]"
      :views="['table', 'cards']"
      :card-breakpoint="CARD_BREAKPOINT"
      :hide-toolbar-when-empty="!filtered"
      :loading="state.loading.value"
      :error="loadError"
      :search-placeholder="$t('billing.invoices.search')"
      :labels="labels"
      :entity-label="entityLabel"
      :columns="columns"
      :actions="actions"
      :card-title="invoiceName"
      :card-icon="() => 'ion:receipt-outline'"
      @page-change="goToPage"
      @load-more="windowPages += 1"
      @page-size-change="setPageSize"
      @action="onAction"
      @retry="state.retry()"
    >
      <template #filters>
        <InvoiceFilters
          :businesses="options"
          :years="years"
          :business="hubId"
          :status="status"
          :year="year"
          @change="setFilter"
          @clear="clearFilters"
        />
      </template>

      <template #toolbar>
        <ion-button
          v-if="selected.length"
          class="invoices-tool"
          size="small"
          fill="outline"
          data-testid="invoices-pdf-selected"
          @click="downloadSelected"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
            aria-hidden="true"
          />
          {{ $t('billing.invoices.pdfSelected', { count: selected.length }) }}
        </ion-button>
        <ion-button
          ref="csvButton"
          class="invoices-tool invoices-csv"
          size="small"
          fill="outline"
          data-testid="invoices-csv"
          :title="$t('billing.invoices.csvHint')"
          :aria-label="$t('billing.invoices.csv')"
          @click="downloadCsv"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
            aria-hidden="true"
          />
          <span class="csv-label--long">{{ $t('billing.invoices.csv') }}</span>
          <span
            class="csv-label--short"
            aria-hidden="true"
          >{{ $t('billing.invoices.csvShort') }}</span>
        </ion-button>
      </template>

      <template #number="{ row }">
        <span class="invoice-number">
          <span class="invoice-number__name">{{ invoiceName(row) }}</span>
          <span
            v-if="row.kind === 'credit_note'"
            class="invoice-number__kind"
            data-testid="invoice-kind"
            :title="creditNoteLabel(row)"
          >{{ creditNoteLabel(row) }}</span>
          <button
            v-if="rectified.get(row.id)"
            type="button"
            class="invoice-number__link"
            data-testid="invoice-rectifies"
            @click="showRectified(rectified.get(row.id) ?? '')"
          >{{ $t('billing.invoices.rectifies', { number: rectified.get(row.id) }) }}</button>
        </span>
      </template>
      <template #status="{ row }">
        <StatusPill
          v-bind="invoicePill(row, locale)"
          size="sm"
        />
      </template>

      <template #empty>
        <div
          class="invoices-empty"
          data-testid="invoices-empty"
        >
          <span class="invoices-empty__icon"><HubIcon
            :name="filtered ? 'ion:file-tray-outline' : 'ion:receipt-outline'"
            aria-hidden="true"
          /></span>
          <template v-if="filtered">
            <span>{{ freeBusiness ? $t('billing.invoices.empty.freeBusiness', { name: freeBusiness.name }) : $t('billing.invoices.noMatches') }}</span>
            <ion-button
              fill="outline"
              size="small"
              data-testid="invoices-show-all"
              @click="showAll"
            >
              <HubIcon
                slot="start"
                name="ion:close-outline"
                aria-hidden="true"
              />
              {{ $t('billing.invoices.showAll') }}
            </ion-button>
          </template>
          <template v-else>
            <strong class="invoices-empty__title">{{ $t('billing.invoices.empty.title') }}</strong>
            <span>{{ $t('billing.invoices.empty.body') }}</span>
            <WebOnly>
              <ion-button
                router-link="/store/plans"
                data-testid="invoices-empty-plans"
              >
                <HubIcon
                  slot="start"
                  name="lucide:layers"
                  aria-hidden="true"
                />
                {{ $t('billing.invoices.empty.plans') }}
              </ion-button>
            </WebOnly>
          </template>
        </div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
<style scoped>
.invoices {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.invoices-tool {
  margin: 0;
  text-transform: none;
}
/* «Download Excel», «Excel» on a phone: there the toolbar stays on two lines (search, then the rest). */
.csv-label--short {
  display: none;
}
/* Folded (`toolbar-fit.ts`): «Download Excel» is its icon, named by its aria-label, and the search narrows
   (DataTable's own box: 22rem, at least 12rem), so the toolbar keeps one line from 641 px (R-14). */
@media (min-width: 641px) {
  .invoices--compact .csv-label--long {
    display: none;
  }
  .invoices--compact .invoices-csv > ion-icon {
    margin-inline-end: 0;
  }
  .invoices--compact :deep(.data-table__search) {
    flex-basis: 14rem;
  }
}
@media (max-width: 640px) {
  .csv-label--long {
    display: none;
  }
  .csv-label--short {
    display: inline;
  }
  /* A real tap target on a phone (audit 2026-10-14, R-13). */
  .invoices-tool {
    min-height: 44px;
  }
}
.invoice-number {
  display: inline-flex;
  flex-direction: column;
  min-width: 0;
}
.invoice-number__name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.invoice-number__kind {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.invoice-number__link {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: 0.78rem;
  text-align: start;
  color: var(--ion-color-primary);
  text-decoration: underline;
  cursor: pointer;
}
.invoices-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: 28rem;
  text-align: center;
}
.invoices-empty__icon {
  display: grid;
  place-items: center;
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 999px;
  font-size: 26px;
  background: color-mix(in oklab, var(--ion-color-primary) 10%, transparent);
  color: var(--ion-color-primary);
}
.invoices-empty__title {
  font-size: 1rem;
}
.invoices-empty ion-button {
  margin: 0;
  text-transform: none;
}
</style>
