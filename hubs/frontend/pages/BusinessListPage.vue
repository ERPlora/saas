<script setup lang="ts">
// Businesses (`/businesses`): the panel's home (round 17 §2.3; mockups `businesses.html`, README §3b).
// Management, not the launcher: the account's businesses in a server-side DataTable (list or cards;
// cards up to 900 px so names are not cut on a tablet) with their status (and why), plan, role and
// last use; per row what the server says it allows (`can`): «Open» (not while suspended or deleted),
// «Manage» and «Recover». «Delete» is not on the row (README §3b): it lives in the business's Settings.
// Above the table, what waits for an answer: invitations, ownership offers and unpaid invoices (inside
// the apps without a way to pay, README §4). «Create business» opens a dialog: the form, then the
// preparation, then «ready» or why not, following the new business with its own `hubs.business.get`
// (the list may not show it: a search, another page); meanwhile the list shows it «Preparing». Empty,
// the table holds the sign-up form itself. Live data: `hubs.business.list`. Ionic reuses the page:
// `?create=1` (the launcher's «Create another business») is read each time it comes on screen.
import {
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  EmptyState,
  formatDateTime,
  FormModal,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { AppPage, HubIcon, toastError, toastSuccess, useSurface, WebOnly } from '@erplora/ui/shell';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, onIonViewWillEnter } from '@ionic/vue';
import {
  computed,
  effectScope,
  type EffectScope,
  nextTick,
  onMounted,
  onScopeDispose,
  type Ref,
  shallowRef,
  useTemplateRef,
  watch,
} from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import type { BusinessDetailOut, BusinessRowOut, InvitationOut, OwnershipOfferOut } from '../../../frontend/sdk-types';
import { opensAtAll, preparationFailed, reasonKey, statusPill } from '../business-status';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';
import BusinessPreparing from '../components/BusinessPreparing.vue';
import DeclineDialog from '../components/DeclineDialog.vue';
import { useErrorText } from '../error-text';
import { useAcceptInvitation } from '../invitations';
import { useOpenBusiness } from '../open-business';

const PAGE_SIZES = [10, 25, 50, 100];
/** Cards up to here: a tablet in portrait would cut the names (README §3b). */
const CARD_BREAKPOINT = 900;

const { t, locale } = useI18n();
const router = useRouter();
const client = useLiveClient();
const { text } = useErrorText();
const { inApp } = useSurface();
const { open, opening } = useOpenBusiness();
const { accept, accepting } = useAcceptInvitation();
const restore = useCommand('hubs.business.restore');
const acceptOffer = useCommand('hubs.ownership.accept');
const declineOffer = useCommand('hubs.ownership.decline');

// ── The list ──────────────────────────────────────────────────────────────────────────────────
const search = shallowRef('');
const page = shallowRef(0);
const pageSize = shallowRef(50);
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

const live = useLive('hubs.business.list', () => ({
  limit: pageSize.value * windowPages.value,
  offset: page.value * pageSize.value,
  ...(search.value.trim() ? { search: search.value.trim() } : {}),
}));

const rows = computed<BusinessRowOut[]>(() => live.data.value?.rows ?? []);
const invitations = computed<InvitationOut[]>(() => live.data.value?.invitations ?? []);
const offers = computed<OwnershipOfferOut[]>(() => live.data.value?.ownership_offers ?? []);
const unpaid = computed(() => rows.value.filter((row) => row.status === 'past_due' || row.status === 'suspended'));
const searching = computed(() => search.value.trim() !== '');
const firstLoad = computed(() => live.status.value === 'loading' && !live.data.value);

// A page emptied elsewhere steps back to the last page that still has rows.
watch(live.data, (now) => {
  if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
    goToPage(Math.ceil(now.total / pageSize.value) - 1);
  }
});

const columns = computed(() => [
  { key: 'name', label: t('hubs.list.columns.name'), cell: 'name', width: 'minmax(10rem,1.6fr)', priority: 'high' },
  { key: 'host', label: t('hubs.list.columns.host'), cell: 'host', width: 'minmax(9rem,1.4fr)', priority: 'low' },
  { key: 'status', label: t('hubs.list.columns.status'), cell: 'status', width: 'minmax(8rem,1.2fr)', priority: 'high' },
  {
    key: 'plan',
    label: t('hubs.list.columns.plan'),
    width: 'minmax(5.5rem,0.8fr)',
    format: (_: unknown, row: BusinessRowOut) => row.plan?.name ?? '—',
  },
  { key: 'role', label: t('hubs.list.columns.role'), cell: 'role', width: 'minmax(7rem,1fr)' },
  {
    key: 'last_opened_at',
    label: t('hubs.list.columns.lastOpened'),
    width: 'minmax(7rem,1fr)',
    priority: 'low',
    format: (value: unknown) => (value ? formatDateTime(value as string, locale.value) : '—'),
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
  if (!key || key === 'hubs.reason.pastDue' || key === 'hubs.reason.pastDueApp') return '';
  if (key === 'hubs.reason.preparing') return t('hubs.reason.preparingSoon');
  return t(key, { date: formatDateTime(row.purge_after, locale.value) });
}

const pageOf = (row: { id: string }) => `/businesses/${row.id}/summary`;

/** The row's buttons, as the table folds them when its box narrows (README §3b, W-19): «Open» stays,
 *  «Manage» and «Recover» go into «⋮» first. Each is named with its business for a screen reader. */
const actions = computed<DataTableAction<BusinessRowOut>[]>(() => [
  {
    id: 'open',
    label: (row) => t('hubs.common.openName', { name: row.name }),
    icon: 'ion:log-in-outline',
    color: 'primary',
    pinned: true,
    hidden: (row) => !opensAtAll(row),
    disabled: (row) => !row.can.open || !!opening.value,
    loading: (row) => opening.value === row.id,
  },
  {
    id: 'manage',
    label: (row) => t('hubs.list.actions.manageName', { name: row.name }),
    icon: 'ion:settings-outline',
    color: 'primary',
    hidden: (row) => !row.can.manage,
  },
  {
    id: 'restore',
    label: (row) => t('hubs.list.actions.restoreName', { name: row.name }),
    icon: 'ion:refresh-outline',
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
    void toastSuccess(t('hubs.list.restored', { name: business.name }));
  } catch {
    void toastError(text(restore.error.value));
  }
}

// ── Declining and the ownership offers ───────────────────────────────────────────────────────
const declining = shallowRef<InvitationOut | null>(null);
const declineOpen = shallowRef(false);
function askDecline(invitation: InvitationOut): void {
  declining.value = invitation;
  declineOpen.value = true;
}

async function answerOffer(offer: OwnershipOfferOut, yes: boolean): Promise<void> {
  const command = yes ? acceptOffer : declineOffer;
  try {
    await command.run({ id: offer.id });
    void toastSuccess(yes ? t('hubs.list.ownership.accepted', { name: offer.hub.name }) : t('hubs.list.ownership.declined'));
  } catch {
    void toastError(text(command.error.value));
  }
}

// ── «Create business» ─────────────────────────────────────────────────────────────────────────
const createOpen = shallowRef(false);
const creating = shallowRef(false);
const createForm = useTemplateRef<InstanceType<typeof BusinessCreateForm>>('createForm');
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

const phase = computed<'form' | 'preparing' | 'ready' | 'error'>(() => {
  if (!created.value) return 'form';
  const now = createdNow.value;
  if (now && preparationFailed(now)) return 'error';
  return now?.can.open ? 'ready' : 'preparing';
});

// Each step puts the focus on its own button (V-19): a screen reader hears where it is.
const listButton = useTemplateRef<{ $el: HTMLElement }>('listButton');
const openButton = useTemplateRef<{ $el: HTMLElement }>('openButton');
watch(phase, async (now) => {
  if (now === 'form') return;
  await nextTick();
  (now === 'ready' ? openButton.value : listButton.value)?.$el.focus();
});
const createTitle = computed(() => {
  const name = created.value?.name ?? '';
  return {
    form: t('hubs.createModal.title'),
    preparing: t('hubs.createModal.preparingTitle', { name }),
    ready: t('hubs.createModal.readyTitle'),
    error: t('hubs.createModal.errorTitle'),
  }[phase.value];
});

function startCreate(): void {
  created.value = null;
  createOpen.value = true;
}
function onCreated(business: { id: string; name: string; host: string }, extra: { typeName: string | null }): void {
  created.value = { id: business.id, name: business.name, host: business.host, typeName: extra.typeName };
  createOpen.value = true;
}
function closeCreate(): void {
  createOpen.value = false;
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
  <AppPage :title="$t('hubs.list.title')">
    <div class="list-stack">
      <InlineFeedback
        v-if="live.status.value === 'reconnecting'"
        tone="warning"
        data-testid="businesses-reconnecting"
      >
        {{ $t('hubs.common.reconnecting') }}
      </InlineFeedback>

      <InlineFeedback
        v-for="invitation in invitations"
        :key="invitation.id"
        tone="info"
        icon="ion:mail-outline"
        :data-testid="`businesses-invitation-${invitation.id}`"
        :heading="$t('hubs.list.invitation.heading', { name: invitation.hub.name })"
      >
        {{
          invitation.invited_by
            ? $t('hubs.list.invitation.body', { inviter: invitation.invited_by, role: invitation.role_label })
            : $t('hubs.list.invitation.bodyNoInviter', { role: invitation.role_label })
        }}
        <template #actions>
          <ion-button
            data-testid="invitation-accept"
            size="small"
            :disabled="!!accepting"
            @click="accept(invitation)"
          >
            <HubIcon
              slot="start"
              name="ion:checkmark-outline"
            />
            {{ $t('hubs.invitation.accept') }}
          </ion-button>
          <ion-button
            data-testid="invitation-decline"
            size="small"
            fill="outline"
            class="btn-neutral"
            :disabled="!!accepting"
            @click="askDecline(invitation)"
          >
            <HubIcon
              slot="start"
              name="ion:close-outline"
            />
            {{ $t('hubs.invitation.decline') }}
          </ion-button>
        </template>
      </InlineFeedback>

      <InlineFeedback
        v-for="offer in offers"
        :key="offer.id"
        tone="info"
        icon="ion:swap-vertical-outline"
        :data-testid="`businesses-offer-${offer.id}`"
        :heading="$t('hubs.list.ownership.heading', { from: offer.from_email, name: offer.hub.name })"
      >
        {{ $t('hubs.list.ownership.body', { date: formatDateTime(offer.expires_at, $i18n.locale) }) }}
        <template #actions>
          <ion-button
            data-testid="offer-accept"
            size="small"
            :disabled="acceptOffer.pending.value || declineOffer.pending.value"
            @click="answerOffer(offer, true)"
          >
            <HubIcon
              slot="start"
              name="ion:checkmark-outline"
            />
            {{ $t('hubs.list.ownership.accept') }}
          </ion-button>
          <ion-button
            data-testid="offer-decline"
            size="small"
            fill="outline"
            class="btn-neutral"
            :disabled="acceptOffer.pending.value || declineOffer.pending.value"
            @click="answerOffer(offer, false)"
          >
            <HubIcon
              slot="start"
              name="ion:close-outline"
            />
            {{ $t('hubs.list.ownership.decline') }}
          </ion-button>
        </template>
      </InlineFeedback>

      <InlineFeedback
        v-for="row in unpaid"
        :key="row.id"
        tone="danger"
        icon="ion:card-outline"
        :data-testid="`businesses-unpaid-${row.id}`"
        :heading="
          row.status === 'suspended'
            ? $t('hubs.list.unpaid.suspendedHeading', { name: row.name })
            : $t('hubs.list.unpaid.pastDueHeading', { name: row.name })
        "
      >
        {{ row.status === 'suspended' ? $t('hubs.list.unpaid.suspendedBody') : $t('hubs.list.unpaid.pastDueBody') }}
        <WebOnly>
          <template #app>
            {{ $t('hubs.list.unpaid.app') }}
          </template>
        </WebOnly>
      </InlineFeedback>

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
        :rows="rows"
        :total="live.data.value?.total ?? 0"
        :page="page"
        :page-size="pageSize"
        :page-size-options="PAGE_SIZES"
        :views="['table', 'cards']"
        :card-breakpoint="CARD_BREAKPOINT"
        :loading="firstLoad"
        :error="live.status.value === 'error' ? text(live.error.value) : undefined"
        :search-placeholder="$t('hubs.list.search')"
        :labels="labels"
        :entity-label="entityLabel"
        :columns="columns"
        :actions="actions"
        :card-title="(row: BusinessRowOut) => row.name"
        :card-icon="() => 'ion:storefront-outline'"
        @page-change="goToPage"
        @load-more="windowPages += 1"
        @page-size-change="setPageSize"
        @add="startCreate"
        @action="onAction"
        @retry="live.refresh()"
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
          <span
            class="mono"
            data-testid="business-host"
          >{{ row.host }}</span>
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

        <template #card="{ row }">
          <p
            class="mono card-host"
            data-testid="business-host"
          >
            {{ row.host }}
          </p>
          <p class="card-pills">
            <StatusPill v-bind="pill(row)" />
            <span
              v-if="row.plan"
              class="card-meta"
            ><HubIcon name="ion:receipt-outline" />{{ $t('hubs.common.plan', { name: row.plan.name }) }}</span>
            <span
              class="card-meta"
              data-testid="business-role"
            ><HubIcon name="ion:person-outline" />{{ row.role_label }}</span>
            <StatusPill
              v-if="row.last_opened_at && row.id === rows[0]?.id"
              class="tag-recent"
              tone="info"
              :dot="false"
              :label="$t('hubs.common.lastOpened')"
            />
          </p>
          <p
            v-if="why(row) || managedByOwner(row)"
            class="card-why"
            data-testid="business-status-why"
          >
            {{ why(row) || $t('hubs.common.managedByOwner') }}
          </p>
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

    <FormModal
      v-model:open="createOpen"
      testid="create-modal"
      :title="createTitle"
      :submit-label="$t('hubs.create.submit')"
      submit-icon="ion:add-outline"
      :pending="creating"
      @submit="createForm?.submit()"
    >
      <template v-if="phase === 'form'">
        <h2 class="create-heading">
          {{ $t('hubs.create.heading') }}
        </h2>
        <p class="create-lead">
          {{ $t('hubs.create.lead') }}
        </p>
        <BusinessCreateForm
          ref="createForm"
          :submit-button="false"
          @update:pending="creating = $event"
          @created="onCreated"
        />
        <p class="create-foot">
          {{ $t('hubs.create.foot') }}
        </p>
      </template>
      <template v-else-if="phase === 'preparing' && created">
        <p class="create-lead">
          {{ $t('hubs.launch.preparing.lead') }}
        </p>
        <BusinessPreparing
          :name="created.name"
          :type-name="created.typeName"
          last="ready"
        />
        <p class="create-foot">
          {{ $t('hubs.createModal.closeHint') }}
        </p>
      </template>
      <div
        v-else-if="phase === 'ready' && created"
        class="ion-text-center"
      >
        <div class="result-icon is-success">
          <HubIcon name="ion:checkmark-outline" />
        </div>
        <p class="create-lead">
          <i18n-t keypath="hubs.createModal.readyAddress">
            <template #host>
              <span class="mono">{{ createdNow?.host ?? created.host }}</span>
            </template>
          </i18n-t>
        </p>
      </div>
      <div
        v-else-if="created"
        class="ion-text-center"
      >
        <div class="result-icon is-danger">
          <HubIcon name="ion:warning-outline" />
        </div>
        <p class="create-lead">
          {{ $t('hubs.createModal.error', { name: created.name }) }}
        </p>
      </div>

      <template
        v-if="phase !== 'form'"
        #footer
      >
        <ion-button
          ref="listButton"
          data-testid="create-modal-close-list"
          :fill="phase === 'ready' ? 'clear' : 'solid'"
          @click="closeCreate"
        >
          <HubIcon
            slot="start"
            name="ion:storefront-outline"
          />
          {{ $t('hubs.createModal.goToList') }}
        </ion-button>
        <ion-button
          v-if="phase === 'ready' && createdNow"
          ref="openButton"
          data-testid="create-modal-open"
          :disabled="!!opening"
          @click="open(createdNow)"
        >
          <HubIcon
            slot="start"
            name="ion:log-in-outline"
          />
          {{ $t('hubs.common.openBusiness') }}
        </ion-button>
      </template>
    </FormModal>

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
.card-host {
  margin: 0 0 8px;
  font-size: 0.82rem;
  overflow-wrap: anywhere;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.card-pills {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin: 0;
}
.card-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.82rem;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.card-why {
  margin: 8px 0 0;
  font-size: 0.85rem;
  line-height: 1.4;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
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
.create-heading {
  margin: 0 0 4px;
  font-size: 1.05rem;
  font-weight: 600;
}
.create-lead {
  margin: 0 0 16px;
  font-size: 0.9rem;
  line-height: 1.5;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.create-foot {
  margin: 14px 0 0;
  font-size: 0.85rem;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.result-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin: 8px auto 12px;
  border-radius: 999px;
  font-size: 30px;
}
.result-icon.is-success {
  color: var(--ion-color-success);
  background: color-mix(in srgb, var(--ion-color-success) 14%, transparent);
}
.result-icon.is-danger {
  color: var(--ion-color-danger);
  background: color-mix(in srgb, var(--ion-color-danger) 14%, transparent);
}
.btn-neutral {
  --color: var(--ion-text-color);
  --border-color: color-mix(in oklab, var(--ion-text-color) 35%, transparent);
}
</style>
