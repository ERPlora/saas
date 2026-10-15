<script setup lang="ts">
// Account → API keys (mockups `account.html` «keys», README §3b «Claves de API»): the live `accounts.apikey.list`
// (the keys not revoked, the newest first) in a DataTable that turns into cards up to 1180 px — name, prefix
// (`erps_live_…`, how its owner tells it apart), permissions (the server's labels), created, last used, and
// «Expires» (W-F14; an expired key is marked) — with «New key» (NewKeyModal) and, per row, «Revoke», confirmed
// naming that key (W-F8) and said in a toast. Empty — a real answer of the server with no key — it says what a key is
// for and offers the first one; a failed load (an error, or no answer in time) is said with «Retry», never as «no
// keys» (audit 2026-10-14 R-04). Under the table, that the keys of a business are made inside the business. The
// list fills the page (`fill`, Ioan 2026-10-14).
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  formatDateTime,
  StatusPill,
} from '@erplora/ui/components';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import { useLiveState } from '../../../frontend/live-state';
import type { ApiKeyRowOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import NewKeyModal from './NewKeyModal.vue';

/** README §3b: the keys' list is wide (six columns); cards up to 1180 px. */
/** A list from here; its dates fold first (audit 2 R-33: three keys were cards at 1024–1180). */
const CARD_BREAKPOINT = 1000;

const { t, locale } = useI18n();
const { text, forDialog } = useErrorText();
const live = useLive('accounts.apikey.list');
const state = useLiveState(live, { isEmpty: (data) => data.rows.length === 0 });
/** Why the keys could not be loaded: the server's reason, or the connection's after a time-out. */
const loadError = computed(() => (state.failed.value ? text(state.error.value) || t('accounts.account.errors.network') : undefined));
const revoke = useCommand('accounts.apikey.revoke');

const rows = computed<ApiKeyRowOut[]>(() => live.data.value?.rows ?? []);
const scopes = computed(() => live.data.value?.scopes ?? []);
const scopeLabel = computed(() => new Map(scopes.value.map((scope) => [scope.id, scope.label])));
const permissions = (row: ApiKeyRowOut) => row.scopes.map((id) => scopeLabel.value.get(id) ?? id).join(', ');
const date = (value: string | null) => (value ? formatDateTime(value, locale.value) : t('accounts.account.keys.never'));

const columns = computed(() => [
  { key: 'name', label: t('accounts.account.keys.columns.name'), cell: 'name', width: 'minmax(8rem,1fr)', priority: 'high' },
  { key: 'prefix', label: t('accounts.account.keys.columns.prefix'), cell: 'prefix', width: 'minmax(10rem,1.1fr)', sortable: false },
  { key: 'scopes', label: t('accounts.account.keys.columns.permissions'), cell: 'scopes', width: 'minmax(11rem,1.4fr)' },
  { key: 'created_at', label: t('accounts.account.keys.columns.created'), format: (_v, row) => date(row.created_at), priority: 'low' },
  { key: 'last_used_at', label: t('accounts.account.keys.columns.lastUsed'), format: (_v, row) => date(row.last_used_at), priority: 'low' },
  { key: 'expires_at', label: t('accounts.account.keys.columns.expires'), cell: 'expires' },
] satisfies DataTableColumn<ApiKeyRowOut>[]);

const actions = computed<DataTableAction<ApiKeyRowOut>[]>(() => [
  {
    id: 'revoke',
    label: t('accounts.account.keys.revokeShort'),
    icon: 'ion:ban-outline',
    color: 'danger',
    pinned: true,
    showLabel: true,
  },
]);

const creating = shallowRef(false);
const target = shallowRef<ApiKeyRowOut | null>(null);
const revoking = shallowRef(false);

function onAction({ row }: DataTableActionEvent<ApiKeyRowOut>): void {
  target.value = row;
  revoke.error.value = null;
  revoking.value = true;
}

async function confirmRevoke(): Promise<void> {
  const row = target.value;
  if (!row) return;
  try {
    await revoke.run({ id: row.id });
    revoking.value = false;
    void toastSuccess(t('accounts.account.keys.revoked', { name: row.name }));
  } catch {
    // `revoke.error`: the dialog shows it.
  }
}
</script>

<template>
  <DataTable
    testid="api-keys"
    fill
    :title="$t('accounts.account.keys.title')"
    :rows="rows"
    :columns="columns"
    :actions="actions"
    :views="['table', 'cards']"
    :card-breakpoint="CARD_BREAKPOINT"
    :column-picker="rows.length > 0"
    :page-size="25"
    :page-size-options="[25, 50]"
    :page-size-chooser="false"
    hide-toolbar-when-empty
    addable
    :loading="state.loading.value"
    :error="loadError"
    :labels="{ add: $t('accounts.account.keys.new'), loadError: $t('accounts.account.keys.loadError'), retry: $t('accounts.account.retry') }"
    :entity-label="(n: number) => $t('accounts.account.keys.entity', n)"
    :card-title="(row: ApiKeyRowOut) => row.name"
    :card-icon="() => 'ion:key-outline'"
    @add="creating = true"
    @action="onAction"
    @retry="state.retry()"
  >
    <template #name="{ row }">
      <strong>{{ row.name }}</strong>
    </template>
    <template #scopes="{ row }">
      <!-- A div, not the span DataTable clips with «…»: the permissions may wrap (audit 2 R-25). -->
      <div
        class="cell-wrap"
        data-testid="api-key-scopes"
      >
        {{ permissions(row) }}
      </div>
    </template>
    <template #prefix="{ row }">
      <span class="key-prefix">{{ row.prefix }}…</span>
    </template>
    <template #expires="{ row }">
      <span class="key-expires">
        {{ row.expires_at ? date(row.expires_at) : $t('accounts.account.keys.never') }}
        <StatusPill
          v-if="row.expired"
          data-testid="api-key-expired"
          tone="danger"
          size="sm"
          :label="$t('accounts.account.keys.expired')"
        />
      </span>
    </template>
    <template #empty>
      <div
        class="keys-empty"
        data-testid="api-keys-empty"
      >
        <span class="keys-empty__icon">
          <HubIcon
            name="ion:key-outline"
            aria-hidden="true"
          />
        </span>
        <span>{{ $t('accounts.account.keys.empty') }}</span>
        <ion-button
          data-testid="api-keys-empty-new"
          @click="creating = true"
        >
          <HubIcon
            slot="start"
            name="ion:add"
            aria-hidden="true"
          />
          {{ $t('accounts.account.keys.new') }}
        </ion-button>
      </div>
    </template>
  </DataTable>
  <p class="keys-note">
    {{ $t('accounts.account.keys.note') }}
  </p>

  <NewKeyModal
    v-model:open="creating"
    :scopes="scopes"
  />
  <ConfirmDialog
    v-model:open="revoking"
    testid="revoke-key"
    confirm-icon="ion:ban-outline"
    :title="$t('accounts.account.keys.revokeTitle', { name: target?.name ?? '' })"
    :message="$t('accounts.account.keys.revokeMessage')"
    :confirm-label="$t('accounts.account.keys.revoke')"
    :pending="revoke.pending.value"
    :error="forDialog(revoke.error.value)"
    @confirm="confirmRevoke"
  />
</template>

<style scoped>
.cell-wrap {
  min-width: 0;
  white-space: normal;
}
.key-prefix {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
}
.key-expires {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.keys-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  max-width: 28rem;
  text-align: center;
}
.keys-empty__icon {
  display: grid;
  place-items: center;
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 999px;
  font-size: 26px;
  background: color-mix(in oklab, var(--ion-color-primary) 10%, transparent);
  color: var(--ion-color-primary);
}
.keys-empty ion-button {
  margin: 0;
  text-transform: none;
}
.keys-empty ion-button > ion-icon[slot='start'] {
  margin-inline-end: 0.45em;
}
.keys-note {
  margin: -4px 2px 0;
  font-size: 0.82rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
</style>
