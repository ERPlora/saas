<script setup lang="ts">
// Account → Security, «Active sessions» (mockups `account.html` «security», README §3b «Sesiones activas»): the
// live `accounts.session.list` (this session first) in a DataTable — device, browser or app, IP address (the
// location is the IP: no GeoIP, plan §6) and last use. Each row but this one closes on its own
// (`accounts.session.close`); an app's session asks first, since it may be charging at a till (W-F5). «Close
// other sessions» (toolbar) is confirmed with how many go, the apps too (V-33). Closing a session in the SaaS
// also ends it in the businesses (the server asks the Hub). Every close ends in a toast naming where. A failed load
// (an error, or no answer in time) is said with «Retry», never as «no results · 0 sessions» (audit 2026-10-14
// R-04). The list fills what the «Sign-in» card leaves of the page (`fill`, Ioan 2026-10-14).
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  formatDateTime,
  StatusPill,
} from '@erplora/ui/components';
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import { useLiveState } from '../../../frontend/live-state';
import type { SessionRowOut } from '../../../frontend/sdk-types';
import { browserName, deviceIcon, deviceName, isAppSession } from '../devices';
import { useErrorText } from '../error-text';

const { t, locale } = useI18n();
const { text, forDialog } = useErrorText();
const live = useLive('accounts.session.list');
const state = useLiveState(live, { isEmpty: (data) => data.rows.length === 0 });
/** Why the sessions could not be loaded: the server's reason, or the connection's after a time-out. */
const loadError = computed(() => (state.failed.value ? text(state.error.value) || t('accounts.account.errors.network') : undefined));
const close = useCommand('accounts.session.close');
const closeOthers = useCommand('accounts.session.close_others');

const rows = computed<SessionRowOut[]>(() => live.data.value?.rows ?? []);
const others = computed(() => rows.value.filter((row) => !row.is_current).length);
const device = (row: SessionRowOut) => deviceName(t, row.device);

// The server's order stays (this session first, then by last use): no column sorts it away.
const columns = computed(() => [
  { key: 'device', label: t('accounts.account.sessions.columns.device'), cell: 'device', width: 'minmax(10rem,1.5fr)', priority: 'high', sortable: false },
  { key: 'browser', label: t('accounts.account.sessions.columns.browser'), cell: 'browser', sortable: false },
  { key: 'ip', label: t('accounts.account.sessions.columns.ip'), priority: 'low', sortable: false },
  { key: 'last_seen_at', label: t('accounts.account.sessions.columns.lastUsed'), cell: 'lastUsed', sortable: false },
] satisfies DataTableColumn<SessionRowOut>[]);

const target = shallowRef<SessionRowOut | null>(null);
const actions = computed<DataTableAction<SessionRowOut>[]>(() => [
  {
    id: 'close',
    label: t('accounts.account.sessions.close'),
    icon: 'ion:log-out-outline',
    color: 'danger',
    pinned: true,
    showLabel: true,
    hidden: (row) => row.is_current,
    loading: (row) => close.pending.value && target.value?.id === row.id,
  },
]);

const confirmingApp = shallowRef(false);
const confirmingOthers = shallowRef(false);

function onAction({ row }: DataTableActionEvent<SessionRowOut>): void {
  target.value = row;
  close.error.value = null;
  if (isAppSession(row)) confirmingApp.value = true;
  else void closeOne(row);
}

async function closeOne(row: SessionRowOut): Promise<void> {
  try {
    await close.run({ id: row.id });
    confirmingApp.value = false;
    void toastSuccess(t('accounts.account.sessions.closed', { device: device(row) }));
  } catch {
    if (!confirmingApp.value) void toastError(text(close.error.value));
  }
}

function askOthers(): void {
  closeOthers.error.value = null;
  confirmingOthers.value = true;
}

async function closeTheOthers(): Promise<void> {
  try {
    const done = await closeOthers.run({});
    confirmingOthers.value = false;
    void toastSuccess(t('accounts.account.sessions.othersClosed', { n: done.closed }));
  } catch {
    // `closeOthers.error`: the dialog shows it.
  }
}
</script>

<template>
  <DataTable
    testid="sessions"
    fill
    :title="$t('accounts.account.sessions.title')"
    :rows="rows"
    :columns="columns"
    :actions="actions"
    :views="['table', 'cards']"
    :column-picker="false"
    :page-size="25"
    :page-size-options="[25, 50]"
    :page-size-chooser="false"
    :loading="state.loading.value"
    :error="loadError"
    :labels="{ loadError: $t('accounts.account.sessions.loadError'), retry: $t('accounts.account.retry') }"
    :entity-label="(n: number) => $t('accounts.account.sessions.entity', n)"
    :card-title="device"
    :card-icon="(row: SessionRowOut) => deviceIcon(row.device)"
    @action="onAction"
    @retry="state.retry()"
  >
    <template #toolbar>
      <ion-button
        data-testid="sessions-close-others"
        class="close-others"
        size="small"
        fill="outline"
        :disabled="others === 0"
        @click="askOthers"
      >
        <HubIcon
          slot="start"
          name="ion:log-out-outline"
          aria-hidden="true"
        />
        {{ $t('accounts.account.sessions.closeOthers') }}
      </ion-button>
    </template>
    <!-- Divs, not the span DataTable clips with «…»: the browser and the last use may wrap (audit 2 R-25). -->
    <template #browser="{ row }">
      <div
        class="cell-wrap"
        data-testid="session-browser"
      >
        {{ browserName(t, row) }}
      </div>
    </template>
    <template #lastUsed="{ row }">
      <div
        class="cell-wrap"
        data-testid="session-last-used"
      >
        {{ row.is_current ? $t('accounts.account.sessions.now') : formatDateTime(row.last_seen_at, locale) }}
      </div>
    </template>
    <template #device="{ row }">
      <span
        class="session-device"
        data-testid="session-device"
      >
        <strong>{{ device(row) }}</strong>
        <StatusPill
          v-if="row.is_current"
          tone="success"
          size="sm"
          :label="$t('accounts.account.sessions.this')"
        />
      </span>
    </template>
  </DataTable>
  <p class="sessions-note">
    {{ $t('accounts.account.sessions.note') }}
  </p>

  <ConfirmDialog
    v-model:open="confirmingApp"
    testid="session-close-app"
    confirm-icon="ion:log-out-outline"
    :title="$t('accounts.account.sessions.appTitle', { device: target ? device(target) : '' })"
    :message="$t('accounts.account.sessions.appMessage', { device: target ? device(target) : '', ip: target?.ip ?? '' })"
    :confirm-label="$t('accounts.account.sessions.appConfirm')"
    :pending="close.pending.value"
    :error="forDialog(close.error.value)"
    @confirm="target && closeOne(target)"
  />
  <ConfirmDialog
    v-model:open="confirmingOthers"
    testid="sessions-close-others-dialog"
    confirm-icon="ion:log-out-outline"
    :title="$t('accounts.account.sessions.othersTitle')"
    :message="$t('accounts.account.sessions.othersMessage', others)"
    :confirm-label="$t('accounts.account.sessions.othersConfirm', others)"
    :pending="closeOthers.pending.value"
    :error="forDialog(closeOthers.error.value)"
    @confirm="closeTheOthers"
  />
</template>

<style scoped>
.cell-wrap {
  min-width: 0;
  white-space: normal;
}
.session-device {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  min-width: 0;
}
.close-others {
  margin: 0;
  text-transform: none;
}
.close-others > ion-icon[slot='start'] {
  margin-inline-end: 0.45em;
}
.sessions-note {
  margin: -4px 2px 0;
  font-size: 0.82rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
</style>
