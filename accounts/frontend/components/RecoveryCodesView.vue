<script setup lang="ts">
// The recovery codes of the two-factor settings (allauth's `mfa/recovery_codes/index.html`): the unused ones the page
// read, and «Download», a text file built here, so there is no server route for it. The page makes the calls.
import type { RecoveryCodes } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon } from '@ionic/vue';

const props = defineProps<{
  recovery: RecoveryCodes | null;
  busy: boolean;
}>();
defineEmits<{ regenerate: []; back: [] }>();

const DOWNLOAD_NAME = 'erplora-recovery-codes.txt';
/** How long the downloaded file's object URL lives (the browser reads it after the click). */
const DOWNLOAD_URL_TTL_MS = 40_000;
const ICONS = { codes: ionIconSrc('lucide:key-round') };

/** The unused codes as a text file, one per line: built here, never a server route. */
function download(): void {
  const codes = props.recovery?.unusedCodes ?? [];
  const url = URL.createObjectURL(new Blob([`${codes.join('\n')}\n`], { type: 'text/plain' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = DOWNLOAD_NAME;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_TTL_MS);
}
</script>

<template>
  <div data-testid="codes-view">
    <div class="auth-mark">
      <ion-icon
        class="auth-mark-icon"
        :icon="ICONS.codes"
        aria-hidden="true"
      />
    </div>
    <h2 class="auth-title">
      {{ $t('accounts.twoFactor.codes.title') }}
    </h2>
    <p
      class="auth-lead"
      data-testid="codes-lead"
    >
      {{ $t('accounts.twoFactor.codes.lead') }}
    </p>
    <template v-if="recovery?.unusedCodeCount">
      <pre
        v-if="recovery.unusedCodes.length"
        class="recovery-codes"
        data-testid="codes-list"
      >{{ recovery.unusedCodes.join('\n') }}</pre>
      <p
        class="auth-lead"
        data-testid="codes-count"
      >
        {{ $t('accounts.twoFactor.codes.count', { unused: recovery.unusedCodeCount, total: recovery.totalCodeCount }) }}
      </p>
    </template>
    <div
      v-else
      class="non-field-error"
      data-testid="codes-none"
    >
      {{ $t('accounts.twoFactor.codes.noneLeft') }}
    </div>
    <ion-button
      v-if="recovery?.unusedCodes.length"
      data-testid="codes-download"
      fill="outline"
      expand="block"
      @click="download()"
    >
      {{ $t('accounts.twoFactor.codes.download') }}
    </ion-button>
    <ion-button
      data-testid="codes-generate"
      fill="outline"
      expand="block"
      class="after"
      :disabled="busy"
      @click="$emit('regenerate')"
    >
      {{ $t('accounts.twoFactor.codes.generateNew') }}
    </ion-button>
    <ion-button
      data-testid="codes-back"
      fill="clear"
      expand="block"
      class="after"
      :disabled="busy"
      @click="$emit('back')"
    >
      {{ $t('accounts.twoFactor.codes.back') }}
    </ion-button>
  </div>
</template>

<style scoped src="./auth-card.css"></style>
