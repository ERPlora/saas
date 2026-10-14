<script setup lang="ts">
// The icon of a module, from the app catalog (`apps.app.list` → `icon_svg`: the SVG the Hub bakes, cleaned
// with nh3 by the SaaS, `apps/icons.py`). Painted the way every icon of the shell is: `ion-icon` with the SVG
// as its `;utf8,` data URL (`ionIconSrc`), which ion-icon sanitises again and writes into its shadow root —
// the one HTML sink the page's Trusted Types policy admits (`<svg` only) — with the box, `currentColor` and
// the ionicons classes of every other icon, in light and dark. Never `v-html`. Without a usable SVG, the
// catalog's own fallback, `ion:apps-outline`.
import { HubIcon, ionIconSrc } from '@erplora/ui/shell';
import { IonIcon } from '@ionic/vue';
import { computed } from 'vue';

const props = defineProps<{
  /** The catalog's `icon_svg` (may be empty). */
  svg: string;
}>();

const src = computed(() => {
  const svg = props.svg.trim();
  return svg.startsWith('<svg') ? ionIconSrc(svg) : undefined;
});
</script>

<template>
  <ion-icon
    v-if="src"
    :icon="src"
    aria-hidden="true"
  />
  <HubIcon
    v-else
    name="ion:apps-outline"
    aria-hidden="true"
  />
</template>
