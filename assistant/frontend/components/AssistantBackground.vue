<script setup lang="ts">
// The panel's piece beside the pane (`createShell({ chrome: { background } })`, mounted once per signed-in person,
// ASSISTANT-F25): the shared chat's panel, configured as the panel's in main.ts (`SAAS_ASSISTANT`), with the panel's own
// empty conversation — its sentence and three shortcuts, each asked at once. Only for an account that may ask the
// assistant: the device remembers the panel open, and another person on it must not find it so.
import { AssistantEmpty, AssistantPanel, assistantConfig } from '@erplora/ui/components';
import { useSession } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const SHORTCUTS = ['businesses', 'billing', 'create'] as const;

const { t } = useI18n({ useScope: 'global' });
const session = useSession();
const { canUse } = assistantConfig();
const allowed = computed(() => (canUse ? canUse(session) : true));
const shortcuts = computed(() => SHORTCUTS.map((key) => t(`saas.assistant.shortcuts.${key}`)));
</script>

<template>
  <AssistantPanel v-if="allowed">
    <template #empty="{ ask }">
      <AssistantEmpty
        :text="t('saas.assistant.empty')"
        :shortcuts="shortcuts"
        @ask="ask"
      />
    </template>
  </AssistantPanel>
</template>
