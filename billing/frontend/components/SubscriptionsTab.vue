<script setup lang="ts">
// Billing → Subscriptions (mockups `billing.html`; README §3b and §4; UX-AUDIT-4 W-F1, W-F7, W-F10, X-15;
// PLAN-SAAS §3.6 point 11): one row per business Stripe bills, live (`billing.subscription.list`), in a
// DataTable that turns into cards below 1000 px (its modules and next invoice fold first; audit 2 R-33) —
// business, plan at its net price (and a downgrade waiting for the end of the period), its paid modules (net; «(until …)» kept on one line when cancelled), the next
// invoice with VAT («Free from …» when cancelled) and the status. Per row only what the server computed
// (`actions`): its leading one fixed — «View the invoice» (an unpaid one), «Keep the plan» or «Change plan»
// (the Store with that business) —, and «Cancel plan» (CancelPlanDialog) and «View invoices» in «⋮» («View
// invoices» a button when there is no «⋮»). The list fills the page (`fill`, Ioan 2026-10-14). Changing,
// keeping and cancelling are web only; inside the apps a sentence says where, without a link (README §4).
// Module names come from `apps.app.list` (premium, in the person's language) and plan names and Free's
// limits from `hubs.plan.list`.
import {
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  StatusPill,
  type StatusPillTone,
} from '@erplora/ui/components';
import { HubIcon, toastError, toastSuccess, useSurface, WebOnly } from '@erplora/ui/shell';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { useLiveState } from '../../../frontend/live-state';
import { useErrorText } from '../../../hubs/frontend/error-text';
import type { PlanOut, SubscriptionAction, SubscriptionRowOut } from '../../../frontend/sdk-types';
import { formatDate } from '../format';
import { formatAmount } from '../invoices';
import { isFree } from '../store';
import CancelPlanDialog from './CancelPlanDialog.vue';

/** A row as the table keys and searches it: by its business. */
type Row = SubscriptionRowOut & { id: string; name: string };

/** README §3b: the subscriptions' list is the widest. A list from here; its modules and next invoice fold first
 *  (audit 2 R-33: three rows were cards at 1024–1180). */
const CARD_BREAKPOINT = 1000;
/** What sells or cancels: web only (README §4). */
const WEB_ONLY: ReadonlySet<SubscriptionAction> = new Set(['keep_plan', 'change_plan', 'cancel_plan']);
/** What may lead a row: the server puts the one that applies first («View the invoice» with an unpaid one). */
const LEADS: ReadonlySet<SubscriptionAction> = new Set(['view_invoice', 'keep_plan', 'change_plan']);
const TONES: Readonly<Record<string, StatusPillTone>> = {
  active: 'success',
  trialing: 'info',
  // The mockups' `st-overdue`: red, as the banner that explains it.
  past_due: 'danger',
  unpaid: 'danger',
  incomplete: 'warning',
};

const { t, locale } = useI18n();
const router = useRouter();
const client = useLiveClient();
const { text } = useErrorText();
const { isWeb, surface } = useSurface();
const keep = useCommand('billing.plan.keep');

const live = useLive('billing.subscription.list', { limit: 100 });
const unpaidLive = useLive('billing.invoice.list', { status: 'open', limit: 100 });
const rows = computed<Row[]>(() =>
  (live.data.value?.rows ?? []).map((row) => ({ ...row, id: row.business.id ?? row.business.name, name: row.business.name })),
);
/** Loading, failed (the query, the stream, or nothing in time) or a real answer: never «All your businesses
 *  are on Free» on a failure (audit 2026-10-14, R-04). The unpaid invoices only feed «Cancel plan». */
const state = useLiveState(live, { isEmpty: (data) => data.rows.length === 0 });
const loadError = computed(() => (state.failed.value ? text(state.error.value) || t('billing.load.reason') : undefined));

// ── Names ───────────────────────────────────────────────────────────────────────────────────────
const moduleNames = shallowRef<Record<string, string>>({});
const plans = shallowRef<PlanOut[]>([]);

async function loadModuleNames(): Promise<void> {
  try {
    const { apps } = await client.api.call('apps.app.list', { premium: true });
    moduleNames.value = Object.fromEntries(apps.map((app) => [app.id, app.name]));
  } catch (error) {
    console.error('billing: the names of the modules could not be loaded', error);
  }
}
async function loadPlans(): Promise<void> {
  try {
    plans.value = (await client.api.call('hubs.plan.list')).plans;
  } catch (error) {
    console.error('billing: the plans could not be loaded', error);
  }
}
watch(locale, () => void loadModuleNames(), { immediate: true });
void loadPlans();

const freePlan = computed(() => plans.value.find((plan) => isFree(plan)) ?? null);
const planName = (slug: string) => plans.value.find((plan) => plan.slug === slug)?.name ?? slug;

// ── What each cell says ─────────────────────────────────────────────────────────────────────────
const day = (value: string | null | undefined) => formatDate(value ?? null, locale.value);
const money = (cents: number, currency = 'EUR') => formatAmount(cents, currency, locale.value);
const perPeriod = (cents: number, interval: string) =>
  t(interval === 'year' ? 'billing.modules.perYear' : 'billing.modules.perMonth', { price: money(cents) });

function moduleLines(row: Row) {
  return row.modules.map((module) => {
    const name = moduleNames.value[module.slug] ?? module.slug;
    return {
      slug: module.slug,
      text: module.price_cents === null ? name : `${name} · ${perPeriod(module.price_cents, module.interval)}`,
      until: module.valid_until ? t('billing.subscriptions.until', { date: day(module.valid_until) }) : '',
    };
  });
}

function statusPill(row: Row): { tone: StatusPillTone; label: string } {
  if (row.cancelling) return { tone: 'warning', label: t('billing.subscriptions.statusUntil', { date: day(row.ends_at) }) };
  return { tone: TONES[row.status] ?? 'neutral', label: row.status_label };
}

const columns = computed(() => [
  { key: 'name', label: t('billing.subscriptions.columns.business'), cell: 'business', width: 'minmax(8rem,1.1fr)', priority: 'high' },
  { key: 'plan', label: t('billing.subscriptions.columns.plan'), cell: 'plan', width: 'minmax(7.5rem,0.9fr)', sortable: false },
  { key: 'modules', label: t('billing.subscriptions.columns.modules'), cell: 'modules', width: 'minmax(10rem,1.5fr)', sortable: false, priority: 'low' },
  { key: 'next_invoice', label: t('billing.subscriptions.columns.next'), cell: 'next', width: 'minmax(8.5rem,1.1fr)', sortable: false, priority: 'low' },
  { key: 'status', label: t('billing.subscriptions.columns.status'), cell: 'status', width: 'minmax(8rem,1fr)' },
] satisfies DataTableColumn<Row>[]);

const labels = computed(() => ({ loadError: t('billing.subscriptions.loadError'), retry: t('billing.subscriptions.retry') }));
const entityLabel = (count: number) => t('billing.subscriptions.entity', count);

/** The row's leading action: the first the server lists that this surface may take. */
function leadOf(row: Row): SubscriptionAction | null {
  return row.actions.find((id) => LEADS.has(id) && (isWeb.value || !WEB_ONLY.has(id))) ?? null;
}
const offers = (row: Row, id: SubscriptionAction) => row.actions.includes(id) && (isWeb.value || !WEB_ONLY.has(id));
/** The row has a «⋮» (what cancels lives there): «View invoices» joins it, so the row shows one button. */
const hasMenu = (row: Row) => offers(row, 'cancel_plan');

/**
 * README §3b, W-F7: the row's leading action is fixed and says what it does («View the invoice», «Keep the
 * plan» or «Change plan», one slot for the three: they never apply together); «Cancel plan», with its
 * confirmation, lives in «⋮» (mockups at 1440, UX-AUDIT-4 W-F1). «View invoices» goes into that «⋮» when the
 * row has one, so a row shows one button and its menu (Ioan, 2026-10-14: a clean list, as the mockups paint
 * an unpaid row); without a «⋮» (nothing to cancel, or inside the apps) it stays a button. Few and fixed, the
 * list fits wherever it is a list (from 1000 px; modules and the next invoice fold first).
 */
const actions = computed<DataTableAction<Row>[]>(() => [
  {
    id: 'lead',
    label: (row: Row) => {
      const lead = leadOf(row);
      return lead ? t(`billing.subscriptions.actions.${lead}`) : '';
    },
    color: 'primary',
    pinned: true,
    hidden: (row: Row) => leadOf(row) === null,
    disabled: () => !!keeping.value,
    loading: (row: Row) => keeping.value === row.id,
  },
  {
    id: 'view_invoices',
    label: t('billing.subscriptions.actions.view_invoices'),
    icon: 'ion:list-outline',
    color: 'primary',
    showLabel: true,
    hidden: (row: Row) => !offers(row, 'view_invoices') || hasMenu(row),
  },
  {
    id: 'view_invoices_menu',
    label: t('billing.subscriptions.actions.view_invoices'),
    icon: 'ion:list-outline',
    color: 'primary',
    showLabel: true,
    menuOnly: true,
    hidden: (row: Row) => !offers(row, 'view_invoices') || !hasMenu(row),
  },
  {
    id: 'cancel_plan',
    label: t('billing.subscriptions.actions.cancel_plan'),
    icon: 'ion:close-circle-outline',
    color: 'danger',
    showLabel: true,
    menuOnly: true,
    hidden: (row: Row) => !offers(row, 'cancel_plan'),
  },
]);

// ── Actions ─────────────────────────────────────────────────────────────────────────────────────
const cancelling = shallowRef<Row | null>(null);
const cancelOpen = shallowRef(false);
const keeping = shallowRef<string | null>(null);
const unpaidOf = (row: Row | null) => (row?.unpaid_invoice_id ? (unpaidLive.data.value?.rows.find((invoice) => invoice.id === row.unpaid_invoice_id) ?? null) : null);

function onAction({ actionId: picked, row }: DataTableActionEvent<Row>): void {
  const id = row.business.id;
  const actionId = picked === 'lead' ? leadOf(row) : picked === 'view_invoices_menu' ? 'view_invoices' : picked;
  if (!id || !actionId) return;
  if (actionId === 'change_plan') void router.push({ path: '/store/plans', query: { business: id } });
  else if (actionId === 'view_invoices') void router.push({ path: '/billing/invoices', query: { business: id } });
  else if (actionId === 'view_invoice') void router.push({ path: '/billing/invoices', query: { business: id, status: 'open' } });
  else if (actionId === 'cancel_plan') {
    cancelling.value = row;
    cancelOpen.value = true;
  } else if (actionId === 'keep_plan') void keepPlan(row, id);
}

async function keepPlan(row: Row, id: string): Promise<void> {
  keeping.value = row.id;
  try {
    await keep.run({ hub_id: id });
    void toastSuccess(t('billing.subscriptions.kept', { business: row.name, plan: row.plan.name }));
  } catch {
    void toastError(text(keep.error.value));
  } finally {
    keeping.value = null;
  }
}
</script>

<template>
  <DataTable
    testid="subscriptions"
    fill
    :title="$t('billing.subscriptions.title')"
    :rows="rows"
    :columns="columns"
    :actions="actions"
    :search-keys="['name']"
    :search-placeholder="$t('billing.subscriptions.search')"
    :views="['table', 'cards']"
    :card-breakpoint="CARD_BREAKPOINT"
    :page-size="50"
    :page-size-chooser="false"
    hide-toolbar-when-empty
    :loading="state.loading.value"
    :error="loadError"
    :labels="labels"
    :entity-label="entityLabel"
    :card-title="(row: Row) => row.name"
    card-title-column="name"
    :card-icon="() => 'ion:sync-outline'"
    @action="onAction"
    @retry="state.retry()"
  >
    <template #toolbar>
      <WebOnly>
        <template #app>
          <span
            class="subscriptions-hint"
            data-testid="subscriptions-app-hint"
          >
            <HubIcon
              name="ion:information-circle-outline"
              aria-hidden="true"
            />
            {{ surface === 'account' ? $t('billing.subscriptions.accountHint') : $t('billing.subscriptions.appHint') }}
          </span>
        </template>
      </WebOnly>
    </template>

    <template #business="{ row }">
      <strong class="cell-strong">{{ row.name }}</strong>
    </template>
    <template #plan="{ row }">
      <div class="cell-stack">
        <strong class="cell-strong">{{ row.plan.name }}</strong>
        <span class="cell-sub nowrap">{{ perPeriod(row.plan.price_cents, row.plan.interval) }}</span>
        <span
          v-if="row.scheduled_change"
          class="cell-sub"
          data-testid="subscription-scheduled"
        >{{ $t('billing.subscriptions.scheduled', { plan: planName(row.scheduled_change.plan), date: day(row.scheduled_change.starts_at) }) }}</span>
      </div>
    </template>
    <template #modules="{ row }">
      <div
        v-if="row.modules.length"
        class="cell-stack"
      >
        <span
          v-for="line in moduleLines(row)"
          :key="line.slug"
        >{{ line.text }}<template v-if="line.until">{{ ' ' }}<em
          class="nowrap"
          data-testid="subscription-until"
        >{{ line.until }}</em></template></span>
      </div>
      <span v-else>—</span>
    </template>
    <template #next="{ row }">
      <div
        v-if="row.cancelling"
        class="cell-stack"
      >
        {{ $t('billing.subscriptions.freeFrom', { date: day(row.ends_at) }) }}
      </div>
      <div
        v-else-if="row.next_invoice"
        class="cell-stack"
      >
        <span>{{ row.next_invoice.total_cents === null ? day(row.next_invoice.date) : $t('billing.subscriptions.next', { date: day(row.next_invoice.date), amount: money(row.next_invoice.total_cents, row.next_invoice.currency) }) }}</span>
        <span
          v-if="row.next_invoice.total_cents !== null"
          class="cell-sub"
        >{{ $t('billing.subscriptions.withVat') }}</span>
      </div>
      <span v-else>—</span>
    </template>
    <template #status="{ row }">
      <StatusPill
        v-bind="statusPill(row)"
        size="sm"
      />
    </template>

    <template #empty>
      <div
        class="subscriptions-empty"
        data-testid="subscriptions-empty"
      >
        <span class="subscriptions-empty__icon"><HubIcon
          name="ion:sync-outline"
          aria-hidden="true"
        /></span>
        <strong>{{ $t('billing.subscriptions.empty.title') }}</strong>
        <span>{{ $t('billing.subscriptions.empty.body') }}</span>
        <WebOnly>
          <ion-button
            router-link="/store/plans"
            data-testid="subscriptions-empty-plans"
          >
            <HubIcon
              slot="start"
              name="lucide:layers"
              aria-hidden="true"
            />
            {{ $t('billing.subscriptions.empty.plans') }}
          </ion-button>
        </WebOnly>
      </div>
    </template>
  </DataTable>

  <WebOnly>
    <CancelPlanDialog
      v-model:open="cancelOpen"
      :row="cancelling"
      :module-names="moduleNames"
      :free-plan="freePlan"
      :unpaid="unpaidOf(cancelling)"
    />
  </WebOnly>
</template>

<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
<style scoped>
.cell-stack {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  /* A module's name and price wrap inside the cell instead of being cut. */
  white-space: normal;
  overflow-wrap: anywhere;
}
.cell-strong {
  font-weight: 600;
}
.cell-sub {
  font-size: 0.8rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.nowrap {
  white-space: nowrap;
}
em.nowrap {
  font-style: normal;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.subscriptions-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.subscriptions-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: 28rem;
  text-align: center;
}
.subscriptions-empty__icon {
  display: grid;
  place-items: center;
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 999px;
  font-size: 26px;
  background: color-mix(in oklab, var(--ion-color-primary) 10%, transparent);
  color: var(--ion-color-primary);
}
.subscriptions-empty ion-button {
  margin: 0;
  text-transform: none;
}
</style>
