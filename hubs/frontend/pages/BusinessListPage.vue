<script setup lang="ts">
// Businesses (`/dashboard/businesses`): the panel's home.
// Management, not the launcher: the account's businesses in a server-side DataTable (list or cards;
// cards up to 900 px so names are not cut on a tablet) with their status (and why), plan, role and
// last use; per row what the server says it allows (`can`): «Open» (not while suspended or deleted),
// «Manage» and «Recover». «Delete» is not on the row: it lives in the business's Settings.
// Above the table, what waits for an answer: invitations and ownership offers (`InvitationsAndOffers`; an unpaid
// invoice is said by the shell's bell, not here). «Create business» opens its dialog (`BusinessCreateModal`); the
// page follows the new business with its own `hubs.business.get` (the list may not show it: a search, another
// page) and hands it to the dialog, while the list shows it «Preparing». Empty, the table holds the sign-up form
// itself, and a business created there is followed by the same dialog. Live data: `hubs.business.list`. Ionic
// reuses the page: `?create=1` (the launcher's «Create another business») is read each time it comes on screen.
// The list fills the page between the topbar and the footer (`detail-fill` + `.panel-fill`), and asks for rows per
// page only when there are more businesses than the shortest page. Its states are truthful (`useLiveState`): the
// stream down or no answer in time is an error with «Retry», never «Create your first business».
import {
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  EmptyState,
  formatDateTime,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { AppPage, HubIcon, toastError, toastSuccess, useSurface } from '@erplora/ui/shell';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, onIonViewWillEnter } from '@ionic/vue';
import {
  computed,
  effectScope,
  type EffectScope,
  onMounted,
  onScopeDispose,
  type Ref,
  shallowRef,
  watch,
} from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { BUSINESSES } from '../../../accounts/frontend/paths';
import { useLiveState } from '../../../frontend/live-state';
import type { BusinessDetailOut, BusinessRowOut, InvitationOut, OwnershipOfferOut } from '../../../frontend/sdk-types/hubs';
import { opensAtAll, reasonDate, reasonKey, statusPill } from '../business-status';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';
import BusinessCreateModal from '../components/BusinessCreateModal.vue';
import DeclineDialog from '../components/DeclineDialog.vue';
import HostName from '../components/HostName.vue';
import InvitationsAndOffers from '../components/InvitationsAndOffers.vue';
import { useErrorText } from '../error-text';
import { useOpenBusiness } from '../open-business';

const PAGE_SIZES = [10, 25, 50, 100];
/** Cards up to here: a tablet in portrait would cut the names. */
const CARD_BREAKPOINT = 900;

const { t, locale } = useI18n();
const router = useRouter();
const client = useLiveClient();
const { text } = useErrorText();
const { inApp } = useSurface();
const { open, opening } = useOpenBusiness();
const restore = useCommand('hubs.business.restore');

// ── The list ──────────────────────────────────────────────────────────────────────────────────
const search = shallowRef('');
const page = shallowRef(0);
const pageSize = shallowRef(50);
/** Pages the live window holds: 1 on a desk; each end of the scroll on a phone adds one. */
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

const live = useLive('hubs.business.list', () => ({
  limit: pageSize.value * windowPages.value,
  offset: page.value * pageSize.value,
  ...(search.value.trim() ? { search: search.value.trim() } : {}),
}));

const state = useLiveState(live, { isEmpty: (data) => data.rows.length === 0 });
/** Why the list could not be loaded: the server's sentence, or the connection hint after the time limit. */
const loadError = computed(() => (state.failed.value ? text(state.error.value) || t('saas.load.body') : undefined));

const rows = computed<BusinessRowOut[]>(() => live.data.value?.rows ?? []);
const invitations = computed<InvitationOut[]>(() => live.data.value?.invitations ?? []);
const offers = computed<OwnershipOfferOut[]>(() => live.data.value?.ownership_offers ?? []);
const searching = computed(() => search.value.trim() !== '');

// A page emptied elsewhere steps back to the last page that still has rows.
watch(live.data, (now) => {
  if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
    goToPage(Math.ceil(now.total / pageSize.value) - 1);
  }
});

const columns = computed(() => [
  { key: 'name', label: t('hubs.list.columns.name'), cell: 'name', width: 'minmax(10rem,1.6fr)', priority: 'high' },
  { key: 'host', label: t('hubs.list.columns.host'), cell: 'host', width: 'minmax(9rem,1.4fr)', priority: 'low', cardIcon: 'ion:globe-outline' },
  { key: 'status', label: t('hubs.list.columns.status'), cell: 'status', width: 'minmax(8rem,1.2fr)', priority: 'high' },
  {
    key: 'plan',
    label: t('hubs.list.columns.plan'),
    format: (_: unknown, row: BusinessRowOut) => row.plan?.name ?? '—',
    cardIcon: 'ion:receipt-outline',
  },
  { key: 'role', label: t('hubs.list.columns.role'), cell: 'role', width: 'minmax(7rem,1fr)', cardIcon: 'ion:person-outline' },
  {
    key: 'last_opened_at',
    label: t('hubs.list.columns.lastOpened'),
    priority: 'low',
    format: (value: unknown) => (value ? formatDateTime(value as string, locale.value) : '—'),
    cardIcon: 'ion:time-outline',
  },
] satisfies DataTableColumn<BusinessRowOut>[]);

const labels = computed(() => ({
  add: t('hubs.list.create'),
  loadError: t('hubs.list.loadError'),
  retry: t('hubs.common.retry'),
}));
const entityLabel = computed(() => ({ one: t('hubs.list.recordSingular'), many: t('hubs.list.recordPlural') }));

// ── What a row says and allows ────────────────────────────────────────────────────────────────
// The buttons are the server's `can` (open, manage, restore); the page only says, for whoever does not
// manage a business, that its owner does.
const managedByOwner = (row: BusinessRowOut) => !row.can.manage && row.role !== 'hub_owner';
const pill = (row: BusinessRowOut) => statusPill(row, t, locale.value);

function why(row: BusinessRowOut): string {
  const key = reasonKey(row, inApp.value);
  // A payment pending is said by the bell of the topbar, with its way to pay.
  if (!key || row.status === 'past_due') return '';
  if (key === 'hubs.reason.preparing') return t('hubs.reason.preparingSoon');
  return t(key, { date: reasonDate(row, locale.value) });
}

const pageOf = (row: { id: string }) => `${BUSINESSES}/${row.id}/summary`;

/** The row's buttons, as the table folds them when its box narrows: «Open» stays,
 *  «Manage» and «Recover» go into «⋮» first. Each says its action in short words; its name adds the business. */
const actions = computed<DataTableAction<BusinessRowOut>[]>(() => [
  {
    id: 'open',
    label: t('hubs.common.open'),
    icon: 'ion:log-in-outline',
    color: 'primary',
    pinned: true,
    hidden: (row) => !opensAtAll(row),
    disabled: (row) => !row.can.open || !!opening.value,
    loading: (row) => opening.value === row.id,
  },
  {
    id: 'manage',
    label: t('hubs.list.actions.manage'),
    icon: 'ion:settings-outline',
    color: 'primary',
    hidden: (row) => !row.can.manage,
  },
  {
    id: 'restore',
    label: t('hubs.list.actions.restore'),
    icon: 'ion:arrow-undo-outline',
    color: 'primary',
    hidden: (row) => !row.can.restore,
    loading: () => restore.pending.value,
  },
]);

function onAction({ actionId, row }: DataTableActionEvent<BusinessRowOut>): void {
  if (actionId === 'open') void open(row);
  else if (actionId === 'manage') void router.push(pageOf(row));
  else if (actionId === 'restore') void recover(row);
}

async function recover(row: BusinessRowOut): Promise<void> {
  try {
    const business = await restore.run({ id: row.id });
    toastSuccess(t('hubs.list.restored', { name: business.name }));
  } catch {
    toastError(text(restore.error.value));
  }
}

// ── Declining an invitation ──────────────────────────────────────────────────────────────────
const declining = shallowRef<InvitationOut | null>(null);
const declineOpen = shallowRef(false);
function askDecline(invitation: InvitationOut): void {
  declining.value = invitation;
  declineOpen.value = true;
}

// ── «Create business» ─────────────────────────────────────────────────────────────────────────
const createOpen = shallowRef(false);
const created = shallowRef<{ id: string; name: string; host: string; typeName: string | null } | null>(null);

// The new business is followed on its own (`hubs.business.get`): the list may not show it (a search,
// another page). A scope per business, stopped when the dialog lets it go.
let following: EffectScope | null = null;
const followed = shallowRef<{ data: Readonly<Ref<BusinessDetailOut | undefined>> } | null>(null);
watch(created, (now) => {
  following?.stop();
  following = null;
  followed.value = null;
  if (!now) return;
  following = effectScope();
  followed.value = following.run(() => ({ data: useLive('hubs.business.get', { id: now.id }, { client }).data })) ?? null;
});
onScopeDispose(() => following?.stop());
const createdNow = computed(() => followed.value?.data.value);

function startCreate(): void {
  created.value = null;
  createOpen.value = true;
}
function onCreated(business: { id: string; name: string; host: string }, extra: { typeName: string | null }): void {
  created.value = { id: business.id, name: business.name, host: business.host, typeName: extra.typeName };
  createOpen.value = true;
}
watch(createOpen, (isOpen) => {
  if (!isOpen) created.value = null;
});

/** Each time the page comes on screen: the launcher's «Create another business» (`?create=1`). */
function entered(): void {
  const current = router.currentRoute.value;
  if (current.query.create !== '1') return;
  startCreate();
  void router.replace({ path: current.path });
}
onMounted(entered);
onIonViewWillEnter(entered);
</script>

<template>
  <AppPage
    :title="$t('hubs.list.title')"
    content-layout="detail-fill"
  >
    <div class="list-stack panel-fill">
      <InlineFeedback
        v-if="state.reconnecting.value"
        tone="warning"
        data-testid="businesses-reconnecting"
      >
        {{ $t('hubs.common.reconnecting') }}
      </InlineFeedback>

      <InvitationsAndOffers
        :invitations="invitations"
        :offers="offers"
        @decline="askDecline"
      />

      <p
        v-if="rows.length"
        class="list-lead"
        data-testid="businesses-lead"
      >
        {{ $t('hubs.list.lead') }}
      </p>

      <DataTable
        v-model:search="query"
        testid="businesses"
        server-side
        searchable
        addable
        fill
        :rows="rows"
        :total="live.data.value?.total ?? 0"
        :page="page"
        :page-size="pageSize"
        :page-size-options="PAGE_SIZES"
        :page-size-chooser="(live.data.value?.total ?? 0) > PAGE_SIZES[0]"
        :views="['table', 'cards']"
        :card-breakpoint="CARD_BREAKPOINT"
        :loading="state.loading.value"
        :error="loadError"
        :search-placeholder="$t('hubs.list.search')"
        :labels="labels"
        :entity-label="entityLabel"
        :columns="columns"
        :actions="actions"
        :card-title="(row: BusinessRowOut) => row.name"
        card-title-column="name"
        :card-icon="() => 'ion:storefront-outline'"
        @page-change="goToPage"
        @load-more="windowPages += 1"
        @page-size-change="setPageSize"
        @add="startCreate"
        @action="onAction"
        @retry="state.retry()"
      >
        <template #name="{ row }">
          <RouterLink
            v-if="row.can.manage"
            class="business-name"
            data-testid="business-name"
            :to="pageOf(row)"
          >
            {{ row.name }}
          </RouterLink>
          <button
            v-else-if="row.can.open"
            type="button"
            class="business-name business-name--open"
            data-testid="business-name"
            :aria-label="$t('hubs.common.openName', { name: row.name })"
            @click="open(row)"
          >
            {{ row.name }}
          </button>
          <strong
            v-else
            class="business-name"
            data-testid="business-name"
          >{{ row.name }}</strong>
        </template>
        <template #host="{ row }">
          <!-- A div, not the span DataTable clips with «…»: the address may take a second line, after a dot. -->
          <div
            class="mono cell-wrap"
            data-testid="business-host"
          >
            <HostName :host="row.host" />
          </div>
        </template>
        <template #status="{ row }">
          <span class="cell-stack">
            <StatusPill v-bind="pill(row)" />
            <small
              v-if="why(row)"
              class="cell-sub"
              data-testid="business-status-why"
            >{{ why(row) }}</small>
          </span>
        </template>
        <template #role="{ row }">
          <span
            class="cell-stack"
            data-testid="business-role"
          >
            <span>{{ row.role_label }}</span>
            <small
              v-if="managedByOwner(row)"
              class="cell-sub"
            >{{ $t('hubs.common.managedByOwner') }}</small>
          </span>
        </template>

        <template #empty>
          <EmptyState
            v-if="searching"
            data-testid="businesses-no-results"
            icon="ion:file-tray-outline"
            :heading="$t('hubs.list.noResults.heading')"
            :message="$t('hubs.list.noResults.message')"
          >
            <template #action>
              <ion-button
                data-testid="businesses-show-all"
                fill="outline"
                @click="query = ''"
              >
                <HubIcon
                  slot="start"
                  name="ion:close-outline"
                  aria-hidden="true"
                />
                {{ $t('hubs.list.noResults.showAll') }}
              </ion-button>
            </template>
          </EmptyState>
          <div
            v-else
            class="empty-create"
            data-testid="businesses-empty"
          >
            <EmptyState
              icon="ion:storefront-outline"
              :heading="$t('hubs.list.empty.heading')"
              :message="$t('hubs.list.empty.message')"
            />
            <div class="empty-create__form">
              <BusinessCreateForm @created="onCreated" />
              <p class="empty-create__foot">
                {{ $t('hubs.list.empty.invited') }}
              </p>
            </div>
          </div>
        </template>
      </DataTable>
    </div>

    <BusinessCreateModal
      v-model:open="createOpen"
      :created="created"
      :created-now="createdNow"
      :free-business="live.data.value?.free_business ?? null"
      :opening="opening"
      @created="onCreated"
      @open="open"
    />

    <DeclineDialog
      v-model:open="declineOpen"
      :invitation="declining"
    />
  </AppPage>
</template>

<style scoped src="../components/buttons.css"></style>
<style scoped>
.list-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.list-lead {
  margin: 0;
  font-size: 0.82rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.business-name {
  font-weight: 600;
  color: var(--ion-text-color);
  text-decoration: none;
}
/* A business the account only works in: its name opens it, as a link would. */
.business-name--open {
  border: 0;
  background: none;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  color: var(--ion-text-color);
}
.business-name--open:hover {
  text-decoration: underline;
}
a.business-name:hover {
  text-decoration: underline;
}
.mono {
  font-family: var(--font-mono, ui-monospace, monospace);
}
/* A cell that may take a second line instead of «…». */
.cell-wrap {
  min-width: 0;
  white-space: normal;
}
.cell-stack {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  min-width: 0;
}
.cell-sub {
  white-space: normal;
  font-size: 0.75rem;
  color: color-mix(in oklab, var(--ion-text-color) 62%, transparent);
}
.empty-create {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
}
.empty-create__form {
  width: 100%;
  text-align: start;
  max-width: 420px;
  margin-bottom: 24px;
}
.empty-create__foot {
  margin: 12px 0 0;
  font-size: 0.78rem;
  line-height: 1.5;
  text-align: center;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
</style>
