<script setup lang="ts">
// The Members of a business (mockups `business.html` «members», round 17 §2.7–2.8, README §3b): the
// live `hubs.member.list` in a server-side DataTable (cards up to 900 px) — name (the account's own row
// marked), email, role, status and last access — and, per row, ONLY the actions the server computed
// for the account (`actions`, in its fixed order: change role, remove, resend, cancel the invitation,
// transfer the ownership). «Invite» when the account may invite (`invitable_roles`). Under the table,
// the places of the plan and what each role may do; above it, a pending ownership offer the owner can
// withdraw. Each action is a dialog of its own; «Resend» needs none.
import {
  businessStatusPill,
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  formatDateTime,
  InlineFeedback,
  StatusPill,
  type StatusPillSpec,
} from '@erplora/ui/components';
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessDetailOut, MemberAction, MemberRowOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import InviteModal from './InviteModal.vue';
import RemoveDialog from './RemoveDialog.vue';
import RoleModal from './RoleModal.vue';
import TransferDialog from './TransferDialog.vue';

const props = defineProps<{
  business: Pick<BusinessDetailOut, 'id' | 'name' | 'pending_transfer'>;
}>();

const PAGE_SIZES = [10, 25, 50, 100];
const CARD_BREAKPOINT = 900;

/** How each server action is painted: its icon, its text and its tone. */
const ACTIONS: Record<MemberAction, { icon: string; label: string; named: string; danger?: boolean }> = {
  change_role: { icon: 'ion:create-outline', label: 'hubs.members.actions.changeRole', named: 'hubs.members.actions.changeRoleOf' },
  remove: { icon: 'ion:trash-outline', label: 'hubs.members.actions.remove', named: 'hubs.members.actions.removeName', danger: true },
  resend: { icon: 'ion:mail-outline', label: 'hubs.members.actions.resend', named: 'hubs.members.actions.resendTo' },
  cancel: { icon: 'ion:close-outline', label: 'hubs.members.actions.cancel', named: 'hubs.members.actions.cancelTo', danger: true },
  transfer: { icon: 'ion:swap-vertical-outline', label: 'hubs.members.actions.transfer', named: 'hubs.members.actions.transferTo' },
};

const { t, locale } = useI18n();
const resend = useCommand('hubs.member.resend');
const withdraw = useCommand('hubs.ownership.cancel');
const { text } = useErrorText();
/** A row button's name for a screen reader: an invitation is named by its email (no answer, no name). */
const named = (action: MemberAction, row: MemberRowOut) =>
  t(ACTIONS[action].named, { name: action === 'resend' || action === 'cancel' ? row.email : row.name });

const page = shallowRef(0);
const pageSize = shallowRef(50);
const windowPages = shallowRef(1);
function goToPage(n: number): void {
  page.value = n;
  windowPages.value = 1;
}
function setPageSize(size: number): void {
  pageSize.value = size;
  goToPage(0);
}

const live = useLive('hubs.member.list', () => ({
  hub_id: props.business.id,
  limit: pageSize.value * windowPages.value,
  offset: page.value * pageSize.value,
}));
const rows = computed<MemberRowOut[]>(() => live.data.value?.rows ?? []);
const seats = computed(() => live.data.value?.seats ?? { used: 0, limit: null });
const invitableRoles = computed(() => live.data.value?.invitable_roles ?? []);

watch(live.data, (now) => {
  if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
    goToPage(Math.ceil(now.total / pageSize.value) - 1);
  }
});

const columns = computed(() => [
  { key: 'name', label: t('hubs.members.columns.name'), cell: 'name', width: 'minmax(10rem,1.4fr)', priority: 'high' },
  { key: 'email', label: t('hubs.members.columns.email'), cell: 'email', width: 'minmax(10rem,1.4fr)' },
  { key: 'role_label', label: t('hubs.members.columns.role'), width: 'minmax(6rem,0.9fr)' },
  { key: 'status', label: t('hubs.members.columns.status'), cell: 'status', width: 'minmax(6rem,0.8fr)' },
  { key: 'last_opened_at', label: t('hubs.members.columns.lastAccess'), cell: 'last', width: 'minmax(8rem,1fr)', priority: 'low' },
] satisfies DataTableColumn<MemberRowOut>[]);
const labels = computed(() => ({
  add: t('hubs.members.invite'),
  loadError: t('hubs.members.loadError'),
  retry: t('hubs.common.retry'),
}));
const entityLabel = computed(() => ({ one: t('hubs.members.recordSingular'), many: t('hubs.members.recordPlural') }));

/** The server's actions of each row (`row.actions`), in its order, for the table to fold: «Transfer
 *  ownership» lives only in «⋮» (README §3b: delicate, and confirmed). Named with the member. */
const ORDER: MemberAction[] = ['change_role', 'remove', 'resend', 'cancel', 'transfer'];
const actions = computed<DataTableAction<MemberRowOut>[]>(() =>
  ORDER.map((id) => ({
    id,
    label: (row: MemberRowOut) => named(id, row),
    icon: ACTIONS[id].icon,
    color: ACTIONS[id].danger ? 'danger' : 'primary',
    menuOnly: id === 'transfer',
    hidden: (row: MemberRowOut) => !row.actions.includes(id),
    loading: id === 'resend' ? (row: MemberRowOut) => resend.pending.value && target.value?.id === row.id : undefined,
  })),
);

function pill(row: MemberRowOut): StatusPillSpec {
  if (row.status === 'active') return businessStatusPill('active', locale.value);
  if (row.status === 'pending') return businessStatusPill('pending_invitation', locale.value);
  return { tone: 'neutral', label: row.status_label, busy: false };
}

function lastAccess(row: MemberRowOut): string {
  if (row.status !== 'active' && row.invited_at) return t('hubs.members.invitedOn', { date: formatDateTime(row.invited_at, locale.value) });
  return row.last_opened_at ? formatDateTime(row.last_opened_at, locale.value) : '—';
}

// ── The dialogs ───────────────────────────────────────────────────────────────────────────────
const inviting = shallowRef(false);
const target = shallowRef<MemberRowOut | null>(null);
const roleOpen = shallowRef(false);
const removeOpen = shallowRef(false);
const transferOpen = shallowRef(false);

function onAction({ actionId, row }: DataTableActionEvent<MemberRowOut>): void {
  void act(actionId as MemberAction, row);
}

async function act(action: MemberAction, row: MemberRowOut): Promise<void> {
  target.value = row;
  if (action === 'change_role') roleOpen.value = true;
  else if (action === 'remove' || action === 'cancel') removeOpen.value = true;
  else if (action === 'transfer') transferOpen.value = true;
  else await sendAgain(row);
}

async function sendAgain(row: MemberRowOut): Promise<void> {
  try {
    const sent = await resend.run({ id: row.id });
    void toastSuccess(t('hubs.members.resent', { email: sent.email }));
  } catch {
    void toastError(text(resend.error.value));
  }
}

async function withdrawOffer(id: string): Promise<void> {
  try {
    await withdraw.run({ id });
    void toastSuccess(t('hubs.members.pendingTransfer.cancelled'));
  } catch {
    void toastError(text(withdraw.error.value));
  }
}
</script>

<template>
  <div class="members-stack">
    <InlineFeedback
      v-if="business.pending_transfer"
      tone="warning"
      icon="ion:swap-vertical-outline"
      data-testid="members-transfer"
      :heading="$t('hubs.members.pendingTransfer.heading', { email: business.pending_transfer.to_email })"
    >
      {{ $t('hubs.members.pendingTransfer.body', { date: formatDateTime(business.pending_transfer.expires_at, locale) }) }}
      <template #actions>
        <ion-button
          data-testid="members-transfer-cancel"
          size="small"
          fill="outline"
          :disabled="withdraw.pending.value"
          @click="withdrawOffer(business.pending_transfer.id)"
        >
          <HubIcon
            slot="start"
            name="ion:close-outline"
          />
          {{ $t('hubs.members.pendingTransfer.cancel') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <DataTable
      testid="members"
      server-side
      :title="$t('hubs.members.title')"
      :rows="rows"
      :total="live.data.value?.total ?? 0"
      :page="page"
      :page-size="pageSize"
      :page-size-options="PAGE_SIZES"
      :views="['table', 'cards']"
      :card-breakpoint="CARD_BREAKPOINT"
      :loading="live.status.value === 'loading' && !live.data.value"
      :error="live.status.value === 'error' ? text(live.error.value) : undefined"
      :addable="invitableRoles.length > 0"
      :labels="labels"
      :entity-label="entityLabel"
      :columns="columns"
      :actions="actions"
      :card-title="(row: MemberRowOut) => row.name"
      :card-icon="() => 'ion:person-outline'"
      @page-change="goToPage"
      @load-more="windowPages += 1"
      @page-size-change="setPageSize"
      @add="inviting = true"
      @action="onAction"
      @retry="live.refresh()"
    >
      <template #name="{ row }">
        <span class="member-name">
          <strong>{{ row.name }}</strong>
          <span
            v-if="row.is_me"
            class="member-you"
            data-testid="member-you"
          >{{ $t('hubs.members.you') }}</span>
        </span>
      </template>
      <template #email="{ row }">
        <span class="member-email">{{ row.email }}</span>
      </template>
      <template #status="{ row }">
        <StatusPill v-bind="pill(row)" />
      </template>
      <template #last="{ row }">
        <span
          class="member-last"
          data-testid="member-last"
        >{{ lastAccess(row) }}</span>
      </template>

      <template #card="{ row }">
        <p class="card-line member-email">
          {{ row.email }}
          <span
            v-if="row.is_me"
            class="member-you"
            data-testid="member-you"
          >{{ $t('hubs.members.you') }}</span>
        </p>
        <p class="card-line">
          <StatusPill v-bind="pill(row)" />
          <span class="card-meta">{{ row.role_label }}</span>
        </p>
        <p
          class="card-line card-meta"
          data-testid="member-last"
        >
          {{ lastAccess(row) }}
        </p>
      </template>
    </DataTable>

    <p
      v-if="seats.limit !== null"
      class="members-seats"
      data-testid="members-seats"
    >
      {{ $t('hubs.members.seats', { used: seats.used, limit: seats.limit }) }}
    </p>

    <InlineFeedback
      tone="neutral"
      data-testid="members-roles"
      :heading="$t('hubs.members.rolesHeading')"
    >
      <span class="roles-line">{{ $t('hubs.members.rolesOwner') }}</span>
      <span class="roles-line">{{ $t('hubs.members.rolesAdmin') }}</span>
      <span class="roles-line">{{ $t('hubs.members.rolesStaff') }}</span>
    </InlineFeedback>

    <InviteModal
      v-model:open="inviting"
      :business="business"
      :invitable-roles="invitableRoles"
      :seats="seats"
    />
    <RoleModal
      v-model:open="roleOpen"
      :member="target"
    />
    <RemoveDialog
      v-model:open="removeOpen"
      :member="target"
      :business-name="business.name"
    />
    <TransferDialog
      v-model:open="transferOpen"
      :member="target"
      :business="business"
    />
  </div>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
.members-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.member-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.member-you {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: color-mix(in oklab, var(--ion-text-color) 60%, transparent);
}
.member-email {
  overflow-wrap: anywhere;
}
.row-action {
  --color: var(--ion-color-primary);
  white-space: nowrap;
  text-transform: none;
}
.member-last {
  white-space: normal;
}
.row-action.is-danger {
  --color: var(--ion-color-danger);
}
.card-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin: 0 0 6px;
}
.card-meta {
  font-size: 0.85rem;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.members-seats {
  margin: -6px 0 0;
  font-size: 0.82rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.roles-line {
  display: block;
}
</style>
