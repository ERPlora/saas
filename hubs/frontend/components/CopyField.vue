<script setup lang="ts">
// A read-only address with «Copy» (mockups `business.html`: «On your devices» and Settings): the text
// in monospace and a copy button; the toast says it was copied, or how to copy it by hand. What is not an
// address (a DNS record of the own domain) brings its own words for the button and the toasts.
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{
  /** What is shown and copied. */
  value: string;
  /** What it is, for a screen reader («Web address of the business»). */
  label: string;
  /** The button's name («Copy address» by default). */
  copyLabel?: string;
  /** The toast once copied («Address copied» by default). */
  copiedText?: string;
  /** The toast when the browser refuses («…copy it by hand» of an address by default). */
  failedText?: string;
}>();

const { t } = useI18n();

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.value);
    void toastSuccess(props.copiedText ?? t('hubs.common.copied'));
  } catch {
    void toastError(props.failedText ?? t('hubs.common.copyFailed'));
  }
}
</script>

<template>
  <div
    class="readonly-field ion-padding-start"
    role="group"
    :aria-label="label"
  >
    <span data-testid="copy-value">{{ value }}</span>
    <ion-button
      data-testid="copy-button"
      fill="clear"
      :aria-label="copyLabel ?? $t('hubs.common.copyAddress')"
      :title="copyLabel ?? $t('hubs.common.copyAddress')"
      @click="copy"
    >
      <HubIcon
        slot="icon-only"
        name="ion:copy-outline"
        aria-hidden="true"
      />
    </ion-button>
  </div>
</template>

<style scoped>
.readonly-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 48px;
  border: 1px solid var(--ion-border-color);
  border-radius: 8px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  overflow-wrap: anywhere;
  color: color-mix(in oklab, var(--ion-text-color) 80%, transparent);
}
.readonly-field ion-button {
  flex: none;
  --color: var(--ion-color-primary);
}
</style>
