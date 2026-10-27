<script setup lang="ts">
// Account (`/dashboard/account/:tab`; round 17, PLAN-SAAS §3.6 point 1; mockups `account.html`): Profile · Security ·
// Preferences · API keys, the footer tabbar of the shell (`AppPage` `tabs`), each section at its own address so
// Back leaves Account instead of walking its tabs. A composition surface: each section is its own component with
// its own live query. Nothing here sells, so it all shows on every surface (deleting the account too: Google Play
// asks for it in the apps); what the account pays is Billing, a section of the menu. Security (its sessions) and
// API keys fill the page between the topbar and the tabbar (`detail-fill` + `.panel-fill`).
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { ACCOUNT } from '../paths';
import ApiKeysTable from '../components/ApiKeysTable.vue';
import PreferencesForm from '../components/PreferencesForm.vue';
import ProfileTab from '../components/ProfileTab.vue';
import SecurityTab from '../components/SecurityTab.vue';

type Tab = 'profile' | 'security' | 'preferences' | 'api-keys';

const props = defineProps<{
  /** The section on screen (the route's `:tab`). */
  tab: Tab;
}>();

const SECTIONS: Array<{ id: Tab; label: string; icon: string }> = [
  { id: 'profile', label: 'accounts.account.tabs.profile', icon: 'lucide:user' },
  { id: 'security', label: 'accounts.account.tabs.security', icon: 'lucide:shield-check' },
  { id: 'preferences', label: 'accounts.account.tabs.preferences', icon: 'lucide:sliders-horizontal' },
  { id: 'api-keys', label: 'accounts.account.tabs.apiKeys', icon: 'lucide:key-round' },
];

const { t } = useI18n();
const tabs = computed<ShellTab[]>(() =>
  SECTIONS.map((section) => ({ id: section.id, label: t(section.label), icon: section.icon, to: `${ACCOUNT}/${section.id}` })),
);
const active = computed(() => props.tab);
/** Security (the sessions) and API keys are lists: they fill the page between the topbar and the tabbar
 *  (Ioan, 2026-10-14). */
const fills = computed(() => props.tab === 'security' || props.tab === 'api-keys');
</script>

<template>
  <AppPage
    :title="$t('accounts.account.title')"
    :content-layout="fills ? 'detail-fill' : 'detail'"
    :tabs="tabs"
    :tabs-label="$t('accounts.account.tabsLabel')"
  >
    <div
      class="account-stack"
      :class="{ 'panel-fill': fills }"
    >
      <ProfileTab v-if="active === 'profile'" />
      <SecurityTab v-else-if="active === 'security'" />
      <PreferencesForm v-else-if="active === 'preferences'" />
      <ApiKeysTable v-else />
    </div>
  </AppPage>
</template>

<style scoped>
.account-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
