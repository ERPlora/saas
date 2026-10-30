<script setup lang="ts">
// «Download the data» on a business's Summary (PLAN-DB round 2026-10-30, proposals (a), (k), (l); HUBS-F18, HUBS-F20):
// the copies the Hub keeps of the business's data, newest first (`hubs.data_copy.list`: when, which, how big), each
// downloaded with a fresh link of the Hub's asked on the click (`hubs.data_copy.link`; it lasts 15 minutes, so a page
// left open still downloads and the mail's link, which leads here, never expires). Only its owner
// (`can.download_data`, the server's). A deleted business always has the card: «not ready yet, we will let you know»
// while the Hub has no copy (or is away), «this business has no copy» when it has no database of its own (`available`
// false: none will ever come), an error with «Retry» when the panel cannot ask. A live business shows it
// only once it has a copy (the one made before its data was reset): nothing while it asks, nothing without one.
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { HubIcon, toastError } from '@erplora/ui/shell';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSkeletonText, IonSpinner } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import { browser } from '../../../billing/frontend/browser';
import type { DataCopyOut } from '../../../frontend/sdk-types';
import { formatBytes } from '../data-copy';
import { useErrorText } from '../error-text';

const props = defineProps<{
  business: { id: string; status: string; can: { download_data: boolean } };
}>();

const { locale } = useI18n();
const { text } = useErrorText();
const list = useCommand('hubs.data_copy.list');
const link = useCommand('hubs.data_copy.link');

const copies = shallowRef<DataCopyOut[] | null>(null);
/** False: the business has no database of its own, so it never gets a copy (nothing is promised). */
const available = shallowRef(true);
const failed = shallowRef<ApiError | null>(null);
/** The copy whose link is being asked (one at a time). */
const opening = shallowRef<string | null>(null);

const deleted = computed(() => props.business.status === 'deleting');
/** A deleted business always has the card; a live one only with a copy to download. */
const shown = computed(
  () => props.business.can.download_data && (deleted.value || (copies.value !== null && copies.value.length > 0)),
);

async function load(): Promise<void> {
  if (!props.business.can.download_data) return;
  failed.value = null;
  copies.value = null;
  try {
    const kept = await list.run({ business_id: props.business.id });
    available.value = kept.available;
    copies.value = kept.copies;
  } catch {
    failed.value = list.error.value;
  }
}

async function download(copy: DataCopyOut): Promise<void> {
  opening.value = copy.id;
  try {
    const { url } = await link.run({ business_id: props.business.id, copy_id: copy.id });
    browser.assign(url);
  } catch {
    void toastError(text(link.error.value));
  } finally {
    opening.value = null;
  }
}

onMounted(load);
</script>

<template>
  <ion-card
    v-if="shown"
    data-testid="data-copy-card"
  >
    <ion-card-content class="ion-padding">
      <div class="page-eyebrow">
        {{ $t('hubs.business.dataCopy.eyebrow') }}
      </div>
      <h2 class="card-title">
        {{ $t('hubs.business.dataCopy.title') }}
      </h2>
      <p class="card-text">
        {{ $t('hubs.business.dataCopy.body') }}
      </p>

      <div
        v-if="failed"
        class="ion-margin-top"
      >
        <InlineFeedback
          tone="danger"
          data-testid="data-copy-error"
          :heading="$t('hubs.business.dataCopy.loadError')"
        >
          {{ text(failed) }}
          <template #actions>
            <ion-button
              size="small"
              fill="outline"
              data-testid="data-copy-retry"
              @click="load"
            >
              {{ $t('hubs.common.retry') }}
            </ion-button>
          </template>
        </InlineFeedback>
      </div>
      <div
        v-else-if="copies === null"
        class="copy-skeleton"
        data-testid="data-copy-loading"
      >
        <ion-skeleton-text
          animated
          style="width: 70%; height: 14px"
        />
        <ion-skeleton-text
          animated
          style="width: 50%; height: 14px"
        />
      </div>
      <InlineFeedback
        v-else-if="!available"
        class="ion-margin-top"
        tone="neutral"
        data-testid="data-copy-none"
      >
        {{ $t('hubs.business.dataCopy.none') }}
      </InlineFeedback>
      <InlineFeedback
        v-else-if="copies.length === 0"
        class="ion-margin-top"
        tone="info"
        data-testid="data-copy-not-ready"
      >
        {{ $t('hubs.business.dataCopy.notReady') }}
      </InlineFeedback>
      <ul
        v-else
        class="copy-list"
      >
        <li
          v-for="copy in copies"
          :key="copy.id"
          class="copy-row"
          data-testid="data-copy-row"
        >
          <div class="copy-row__text">
            <span class="copy-row__when">{{ formatDateTime(copy.created_at, locale) }}</span>
            <span class="copy-row__meta">{{ $t(`hubs.business.dataCopy.kind.${copy.kind}`) }} · {{ formatBytes(copy.bytes, locale) }}</span>
          </div>
          <ion-button
            size="small"
            fill="outline"
            data-testid="data-copy-download"
            :disabled="opening !== null"
            :aria-label="$t('hubs.business.dataCopy.downloadName', { date: formatDateTime(copy.created_at, locale) })"
            @click="download(copy)"
          >
            <ion-spinner
              v-if="opening === copy.id"
              slot="start"
              name="crescent"
              aria-hidden="true"
            />
            <HubIcon
              v-else
              slot="start"
              name="ion:download-outline"
              aria-hidden="true"
            />
            {{ $t('hubs.business.dataCopy.download') }}
          </ion-button>
        </li>
      </ul>
    </ion-card-content>
  </ion-card>
</template>

<style scoped src="./buttons.css"></style>
<style scoped src="./panel-card.css"></style>
<style scoped>
.copy-skeleton {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}
.copy-list {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.copy-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.copy-row__text {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.copy-row__when {
  font-weight: 500;
  color: var(--ion-text-color);
}
.copy-row__meta {
  font-size: 0.85rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
</style>
