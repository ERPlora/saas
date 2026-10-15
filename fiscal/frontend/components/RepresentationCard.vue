<script setup lang="ts">
// The authorisation for ERPlora to file a business's invoices with the AEAT (its representation, VeriFactu), on the
// business's Summary: the live `fiscal.representation.status` (owner and admins). Its state in plain words, a pill
// and a line (the one in force wins over a newer submission still under review, which shows in the history), whose
// it is and who signed it, why it was returned or withdrawn, what the business sent and what is missing, and the
// history of its submissions from two on. Signing and uploading are the Hub's (VeriFactu → Settings): «Manage in your
// business» asks the page to open the business (`manage`), as its «Open» does. The «live» switch is not here.
// Loading: a skeleton; a failure: `LoadFailed`, as every live card of the panel.
import { formatDateTime, StatusPill, type StatusPillTone } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSkeletonText, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { useLiveState } from '../../../frontend/live-state';
import LoadFailed from '../../../frontend/LoadFailed.vue';
import type { RepresentationDocumentsOut, RepresentationState } from '../../../frontend/sdk-types';

type DocumentKey = keyof RepresentationDocumentsOut;

const props = withDefaults(
  defineProps<{
    /** The business (`Hub.id`). */
    id: string;
    /** The business can be opened: «Manage in your business» shows. */
    canManage?: boolean;
    /** The business is being opened: the button waits. */
    managing?: boolean;
  }>(),
  { canManage: false, managing: false },
);

defineEmits<{ manage: [] }>();

const TONES: Record<RepresentationState, StatusPillTone> = {
  none: 'neutral',
  submitted: 'info',
  approved: 'success',
  returned: 'danger',
  revoked: 'warning',
};
/** In the order the Hub asks for them; the first two are required. */
const DOCUMENTS: DocumentKey[] = ['signed_model', 'id_copy', 'signature_sample', 'representation_proof'];
const REQUIRED: DocumentKey[] = ['signed_model', 'id_copy'];

const { t, locale } = useI18n();
const live = useLive('fiscal.representation.status', () => ({ id: props.id }));
const load = useLiveState(live);

const representation = computed(() => live.data.value);
const date = (value: string | null) => formatDateTime(value, locale.value);
const line = computed(() => {
  const now = representation.value;
  if (!now) return '';
  // When it last changed: approved → when it was validated, revoked → when it was withdrawn.
  return t(`fiscal.representation.line.${now.status}`, { date: date(now.changed_at) });
});
const received = computed(() => DOCUMENTS.filter((document) => representation.value?.documents[document]));
const missing = computed(() => {
  const status = representation.value?.status;
  if (status === 'none') return REQUIRED.map((document) => t(`fiscal.representation.documents.${document}`));
  if (status === 'returned' || status === 'revoked') return [t('fiscal.representation.newSubmission')];
  return [];
});
const history = computed(() =>
  (representation.value?.history ?? []).map((entry) => {
    let outcome = t(`fiscal.representation.state.${entry.status}`);
    if (entry.superseded) outcome = t('fiscal.representation.history.superseded');
    else if (entry.status === 'returned' && entry.reason) outcome = t('fiscal.representation.history.returnedWhy', { reason: entry.reason });
    else if (entry.status === 'revoked' && entry.reason) outcome = t('fiscal.representation.history.revokedWhy', { reason: entry.reason });
    return { version: entry.version, text: t('fiscal.representation.history.entry', { version: entry.version, date: date(entry.submitted_at), outcome }) };
  }),
);
</script>

<template>
  <ion-card data-testid="representation">
    <ion-card-content class="ion-padding">
      <div class="page-eyebrow">
        {{ $t('fiscal.representation.eyebrow') }}
      </div>
      <div class="title-row">
        <h2 class="card-title">
          {{ $t('fiscal.representation.title') }}
        </h2>
        <StatusPill
          v-if="representation"
          :tone="TONES[representation.status]"
          :label="$t(`fiscal.representation.state.${representation.status}`)"
          data-testid="representation-pill"
        />
      </div>

      <LoadFailed
        v-if="load.failed.value && !representation"
        class="ion-margin-top"
        :heading="$t('fiscal.representation.loadError')"
        :error="load.error.value"
        :forbidden-heading="$t('fiscal.representation.forbidden')"
        testid="representation-error"
        retry-testid="representation-retry"
        @retry="load.retry()"
      />

      <div
        v-else-if="!representation"
        class="ion-margin-top"
        data-testid="representation-loading"
      >
        <ion-skeleton-text
          animated
          style="width: 90%; height: 12px"
        />
        <ion-skeleton-text
          animated
          style="width: 60%; height: 12px"
        />
      </div>

      <template v-else>
        <p
          class="card-text"
          data-testid="representation-line"
        >
          {{ line }}
        </p>
        <p
          v-if="representation.status === 'submitted'"
          class="card-text small"
          data-testid="representation-sent"
        >
          {{ $t('fiscal.representation.sentOn', { date: date(representation.submitted_at) }) }}
        </p>

        <dl
          v-if="representation.status !== 'none' && (representation.taxpayer_name || representation.signer_name)"
          class="kv"
        >
          <div
            v-if="representation.taxpayer_name"
            data-testid="representation-taxpayer"
          >
            <dt>{{ $t('fiscal.representation.taxpayer') }}</dt>
            <dd>
              {{
                $t('fiscal.representation.taxpayerValue', {
                  name: representation.taxpayer_name,
                  taxId: representation.taxpayer_tax_id,
                })
              }}
            </dd>
          </div>
          <div
            v-if="representation.signer_name"
            data-testid="representation-signer"
          >
            <dt>{{ $t('fiscal.representation.signer') }}</dt>
            <dd>{{ representation.signer_name }}</dd>
          </div>
        </dl>

        <section
          v-if="(representation.status === 'returned' || representation.status === 'revoked') && representation.reason"
          class="reason"
          data-testid="representation-reason"
        >
          <h3 class="section-title">
            {{ $t(`fiscal.representation.reason.${representation.status}`) }}
          </h3>
          <p class="reason__text">
            {{ representation.reason }}
          </p>
        </section>

        <section
          v-if="representation.status !== 'none' && received.length"
          data-testid="representation-received"
        >
          <h3 class="section-title">
            {{ $t('fiscal.representation.received') }}
          </h3>
          <ul class="checklist">
            <li
              v-for="document in received"
              :key="document"
            >
              <HubIcon
                class="tick"
                name="ion:checkmark-circle"
                aria-hidden="true"
              />
              <span>{{ $t(`fiscal.representation.documents.${document}`) }}</span>
            </li>
          </ul>
        </section>

        <section
          v-if="missing.length"
          data-testid="representation-missing"
        >
          <h3 class="section-title">
            {{ $t('fiscal.representation.missing') }}
          </h3>
          <ul class="checklist">
            <li
              v-for="item in missing"
              :key="item"
            >
              <HubIcon
                class="todo"
                name="ion:alert-circle-outline"
                aria-hidden="true"
              />
              <span>{{ item }}</span>
            </li>
          </ul>
        </section>

        <section
          v-if="history.length >= 2"
          data-testid="representation-history"
        >
          <h3 class="section-title">
            {{ $t('fiscal.representation.history.title') }}
          </h3>
          <ol class="history">
            <li
              v-for="entry in history"
              :key="entry.version"
            >
              {{ entry.text }}
            </li>
          </ol>
        </section>
      </template>

      <div
        v-if="canManage && representation"
        class="card-actions"
      >
        <ion-button
          fill="outline"
          data-testid="representation-manage"
          :disabled="managing"
          @click="$emit('manage')"
        >
          <ion-spinner
            v-if="managing"
            slot="start"
            name="crescent"
            aria-hidden="true"
          />
          <HubIcon
            v-else
            slot="start"
            name="ion:log-in-outline"
            aria-hidden="true"
          />
          {{ $t('fiscal.representation.manage') }}
        </ion-button>
      </div>
    </ion-card-content>
  </ion-card>
</template>

<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
<style scoped src="../../../hubs/frontend/components/panel-card.css"></style>
<style scoped>
.title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.section-title {
  margin: 16px 0 6px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.reason {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 10px;
  background: color-mix(in oklab, var(--ion-color-danger) 7%, var(--ion-card-background, #fff));
}
.reason .section-title {
  margin-top: 0;
}
.reason__text {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
  white-space: pre-line;
  overflow-wrap: anywhere;
  color: var(--ion-text-color);
}
.checklist,
.history {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 6px;
  font-size: 0.9rem;
  color: var(--ion-text-color);
}
.checklist li {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tick {
  flex: none;
  font-size: 18px;
  color: var(--ep-success-on-tint, var(--ion-color-success));
}
.todo {
  flex: none;
  font-size: 18px;
  color: color-mix(in oklab, var(--ion-text-color) 55%, transparent);
}
.history li {
  overflow-wrap: anywhere;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
@media (max-width: 599px) {
  .card-actions ion-button {
    flex: 1 1 auto;
    width: 100%;
  }
}
</style>
