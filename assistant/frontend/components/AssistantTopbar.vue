<script setup lang="ts">
// The panel's piece at the end of the topbar (`createShell({ chrome: { topbar } })`, ASSISTANT-F25): the shared chat's
// sparkles «Assistant», which opens and closes its panel (AssistantBackground), only to an account that may ask it
// (`SAAS_ASSISTANT.canUse`). On a phone it stays beside the bell; when a screen puts an action of its own on the bar,
// the shell folds both into «⋮», where the sparkles are the row «Assistant».
import { AssistantButton } from '@erplora/ui/components';
</script>

<template>
  <AssistantButton />
</template>
