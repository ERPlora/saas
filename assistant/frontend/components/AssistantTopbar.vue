<script setup lang="ts">
// The panel's piece at the end of the topbar (`createShell({ chrome: { topbar } })`, ASSISTANT-F25): the shared chat's
// sparkles «Assistant», which opens and closes its panel (AssistantBackground), only to an account that may ask it
// (`SAAS_ASSISTANT.canUse`). Alone in the bar's end group, it never folds into «⋮».
import { AssistantButton } from '@erplora/ui/components';
</script>

<template>
  <AssistantButton />
</template>
