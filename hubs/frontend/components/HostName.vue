<script setup lang="ts">
// A business's web address that breaks only after a dot (audit 2 R-25; W-14 of the mockups): at 390 px the
// launcher split «e2e-billing- / plaza.localhost:8000» at the hyphen, as if it were two addresses. Each part
// between dots stays on one line; a line may end only after a dot (`<wbr>`).
import { computed } from 'vue';

const props = defineProps<{
  host: string;
}>();

/** «panaderia-lopez.», «erplora.», «com»: the dot stays with the part before it. */
const parts = computed(() => props.host.split('.').map((part, index, all) => (index < all.length - 1 ? `${part}.` : part)));
</script>

<template>
  <span class="host-name"><template
    v-for="(part, index) in parts"
    :key="index"
  ><span class="host-name__part">{{ part }}</span><wbr v-if="index < parts.length - 1"></template></span>
</template>

<style scoped>
.host-name__part {
  white-space: nowrap;
}
</style>
