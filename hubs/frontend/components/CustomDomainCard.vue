<script setup lang="ts">
// «Own domain» in a business's Settings (HUBS-F17, saas#195; PLAN-SAAS §8 round 2026-10-22 and §37 point 2): the public
// website of the business on a domain of its owner's, never the app. The live `hubs.custom_domain.get` says whether this
// deployment connects domains (`available`), whether the plan the business has now includes one (`in_plan`) and the
// domain it has; it follows the domain's changes and the plan's. The owner writes `www.…` and asks for it
// (`hubs.custom_domain.request`): the answer brings the two CNAME records to create at once, each with «Copy» — the
// validation one first, which stays for good, and the one that points to ERPlora once the certificate is ready. The
// state and where it is stuck are the server's words (`state_label`, `reason_label`); the hourly check, its last run
// and the failures that count towards the three in a row that stop serving it are said here. A domain that is not
// connected is asked for again (or another one) with the same form; removing it asks first
// (`hubs.custom_domain.remove`). A plan without it says so, with the way to the plans (the Store, only on the web and
// for whoever handles the billing), never a disabled form. Only the owner connects or removes it; an administrator
// reads it. Nothing is shown until the business is there: the query rides the page's first stream
// (FIX-SAAS-BUSINESSES-LIVE-DOUBLE-OPEN), and its loading, error and time-out are `useLiveState`'s.
import {
  ConfirmDialog,
  formatDateTime,
  InlineFeedback,
  type InlineFeedbackTone,
  StatusPill,
  type StatusPillTone,
} from '@erplora/ui/components';
import { HubIcon, toastSuccess, useSurface, WebOnly } from '@erplora/ui/shell';
import { fieldErrors, useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonInput, IonSkeletonText, IonSpinner, IonText } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { STORE } from '../../../accounts/frontend/paths';
import { useLiveState } from '../../../frontend/live-state';
import LoadFailed from '../../../frontend/LoadFailed.vue';
import type {
  BusinessDetailOut,
  CustomDomainReason,
  CustomDomainState,
  CustomDomainStatusOut,
  DnsRecordOut,
} from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import CopyField from './CopyField.vue';

const props = defineProps<{
  /** The business (`Hub.id`), from the address: all the query needs. */
  id: string;
  /** The business once `hubs.business.get` answers; nothing is shown until then. */
  business?: Pick<BusinessDetailOut, 'id' | 'role' | 'plan'> & { can: Pick<BusinessDetailOut['can'], 'manage_billing'> };
}>();

/** The pill of each state: served, on its way (it needs the owner's records), not served, going. */
const STATE_TONES: Record<CustomDomainState, StatusPillTone> = {
  pending: 'warning',
  active: 'success',
  lapsed: 'danger',
  removing: 'neutral',
};
/** Where it is stuck on ERPlora's side: the hourly check tries again by itself, so it is said, not alarmed. */
const RETRIED_BY_ITSELF: ReadonlySet<CustomDomainReason> = new Set([
  'certificate_unavailable',
  'quota_full',
  'dns_unavailable',
  'probe_failed',
]);

const { t, locale } = useI18n();
const { inApp } = useSurface();
const { text, forDialog } = useErrorText();
const live = useLive('hubs.custom_domain.get', () => ({ id: props.id }));
const load = useLiveState(live);
const request = useCommand('hubs.custom_domain.request');
const remove = useCommand('hubs.custom_domain.remove');

/** What the last command answered, until the live query speaks again (its event follows the COMMIT). */
const answered = shallowRef<CustomDomainStatusOut | null>(null);
watch(
  () => live.data.value,
  () => {
    answered.value = null;
  },
);
const status = computed(() => answered.value ?? live.data.value);
const domain = computed(() => status.value?.domain ?? null);

const isOwner = computed(() => props.business?.role === 'hub_owner');
const available = computed(() => !!status.value?.available);
/** The server refuses both commands to anybody but the owner, and everywhere while the deployment connects none. */
const changes = computed(() => isOwner.value && available.value);
/** The form: no domain yet, or one that is not connected (asked for again, or another one in its place). */
const asks = computed(() => changes.value && !!status.value?.in_plan && (!domain.value || domain.value.state === 'lapsed'));
const toPlans = computed(() => `${STORE}/plans?business=${encodeURIComponent(props.id)}`);
const plansWay = computed(() => inApp.value || !!props.business?.can.manage_billing);

const typed = shallowRef('');
// A domain that is not connected comes back in the field, to ask for it again as it is.
watch(
  () => (domain.value?.state === 'lapsed' ? domain.value.domain : ''),
  (lapsed) => {
    if (lapsed && !typed.value) typed.value = lapsed;
  },
  { immediate: true },
);
const errors = computed(() => fieldErrors(request.error.value));
const formError = computed(() => (request.error.value && !errors.value.domain ? text(request.error.value) : ''));

const pill = computed(() => {
  const now = domain.value;
  return now ? { tone: STATE_TONES[now.state], label: now.state_label, busy: now.state === 'removing' } : null;
});
const reason = computed<{ tone: InlineFeedbackTone; text: string } | null>(() => {
  const now = domain.value;
  if (!now || now.state === 'removing') return null;
  if (now.reason) {
    const tone = now.state === 'lapsed' ? 'danger' : RETRIED_BY_ITSELF.has(now.reason) ? 'info' : 'warning';
    return { tone, text: now.reason_label };
  }
  return now.state === 'active' ? { tone: 'success', text: t('hubs.domain.active', { domain: now.domain }) } : null;
});
/** The two records, in the order they are created; the validation one is `null` until ACM has it. */
const records = computed<Array<{ key: 'validation' | 'traffic'; record: DnsRecordOut | null }>>(() => {
  const now = domain.value;
  if (!now || now.state === 'removing') return [];
  return [
    { key: 'validation', record: now.validation },
    { key: 'traffic', record: now.traffic },
  ];
});
const watched = computed(() => domain.value?.state === 'pending' || domain.value?.state === 'active');
const failing = computed(() => (domain.value?.state === 'active' ? domain.value.failures : 0));

const value = (event: CustomEvent<{ value?: unknown }>) => String(event.detail.value ?? '');

async function connect(): Promise<void> {
  const name = typed.value.trim();
  if (!name || request.pending.value) return;
  try {
    const answer = await request.run({ id: props.id, domain: name });
    answered.value = { available: true, in_plan: true, ...status.value, domain: answer };
    typed.value = '';
    void toastSuccess(t('hubs.domain.connected', { domain: answer.domain }));
  } catch {
    // `request.error`: on the field what the server refused of the name, anything else above the button.
  }
}

const confirming = shallowRef(false);
function askToRemove(): void {
  remove.error.value = null;
  confirming.value = true;
}
async function confirmRemove(): Promise<void> {
  const now = domain.value;
  if (!now) return;
  try {
    answered.value = await remove.run({ id: props.id });
  } catch {
    return; // The dialog shows the error.
  }
  confirming.value = false;
  void toastSuccess(t('hubs.domain.removed', { domain: now.domain }));
}
</script>

<template>
  <ion-card
    v-if="business"
    data-testid="custom-domain"
  >
    <ion-card-content class="ion-padding">
      <h2>
        <ion-text color="dark">
          <strong>{{ $t('hubs.domain.title') }}</strong>
        </ion-text>
      </h2>
      <p>{{ $t('hubs.domain.lead') }}</p>

      <div
        v-if="load.loading.value && !status"
        class="ion-margin-top"
        data-testid="domain-loading"
      >
        <ion-skeleton-text animated />
        <ion-skeleton-text animated />
      </div>

      <LoadFailed
        v-else-if="!status"
        class="ion-margin-top"
        :heading="$t('hubs.domain.loadError')"
        :error="load.error.value"
        testid="domain-error"
        retry-testid="domain-retry"
        @retry="load.retry()"
      />

      <template v-else>
        <div
          v-if="domain && pill"
          class="ion-margin-top"
          data-testid="domain-current"
        >
          <div class="ion-display-flex ion-flex-wrap ion-align-items-center ion-justify-content-between">
            <strong data-testid="domain-name">{{ domain.domain }}</strong>
            <StatusPill
              data-testid="domain-state"
              v-bind="pill"
            />
          </div>

          <InlineFeedback
            v-if="reason"
            :tone="reason.tone"
            class="ion-margin-top"
            data-testid="domain-reason"
          >
            {{ reason.text }}
          </InlineFeedback>
          <InlineFeedback
            v-if="domain.state === 'removing'"
            tone="neutral"
            class="ion-margin-top"
            data-testid="domain-removing"
          >
            {{ $t('hubs.domain.removing', { domain: domain.domain }) }}
          </InlineFeedback>
          <InlineFeedback
            v-if="failing > 0"
            tone="warning"
            class="ion-margin-top"
            data-testid="domain-failures"
          >
            {{ $t('hubs.domain.failures', { count: failing }, failing) }}
          </InlineFeedback>

          <div
            v-if="records.length"
            class="ion-margin-top"
          >
            <h3>
              <strong>{{ $t('hubs.domain.records.title') }}</strong>
            </h3>
            <p>{{ $t('hubs.domain.records.lead') }}</p>
            <section
              v-for="item in records"
              :key="item.key"
              class="ion-margin-top"
              :data-testid="`domain-record-${item.key}`"
            >
              <h4>
                <strong>{{ $t(`hubs.domain.${item.key}.title`) }}</strong>
              </h4>
              <p>{{ $t(`hubs.domain.${item.key}.hint`) }}</p>
              <template v-if="item.record">
                <p>
                  {{ $t('hubs.domain.records.type') }}:
                  <strong data-testid="domain-record-type">{{ item.record.type }}</strong>
                </p>
                <p>{{ $t('hubs.domain.records.name') }}</p>
                <CopyField
                  :value="item.record.name"
                  :label="$t('hubs.domain.records.name')"
                  :copy-label="$t('hubs.domain.records.copyName')"
                  :copied-text="$t('hubs.domain.records.copied')"
                  :failed-text="$t('hubs.domain.records.copyFailed')"
                />
                <p>{{ $t('hubs.domain.records.value') }}</p>
                <CopyField
                  :value="item.record.value"
                  :label="$t('hubs.domain.records.value')"
                  :copy-label="$t('hubs.domain.records.copyValue')"
                  :copied-text="$t('hubs.domain.records.copied')"
                  :failed-text="$t('hubs.domain.records.copyFailed')"
                />
              </template>
              <div
                v-else
                data-testid="domain-validation-coming"
              >
                <p>{{ $t('hubs.domain.validation.coming') }}</p>
                <ion-button
                  data-testid="domain-look-again"
                  fill="outline"
                  size="small"
                  @click="live.refresh()"
                >
                  {{ $t('hubs.domain.validation.lookAgain') }}
                </ion-button>
              </div>
            </section>
          </div>

          <div class="ion-margin-top">
            <p
              v-if="watched"
              data-testid="domain-checks"
            >
              {{ $t('hubs.domain.checks') }}
            </p>
            <p
              v-if="domain.checked_at"
              data-testid="domain-checked-at"
            >
              {{ $t('hubs.domain.checkedAt', { date: formatDateTime(domain.checked_at, locale) }) }}
            </p>
            <p
              v-if="domain.state === 'active' && domain.activated_at"
              data-testid="domain-active-since"
            >
              {{ $t('hubs.domain.activeSince', { date: formatDateTime(domain.activated_at, locale) }) }}
            </p>
          </div>
        </div>

        <InlineFeedback
          v-if="!available && !domain"
          tone="info"
          class="ion-margin-top"
          data-testid="domain-unavailable"
        >
          {{ $t('hubs.domain.unavailable') }}
        </InlineFeedback>

        <InlineFeedback
          v-else-if="available && !status.in_plan"
          tone="info"
          class="ion-margin-top"
          data-testid="domain-not-in-plan"
          :heading="
            business.plan
              ? $t('hubs.domain.notInPlan.headingNamed', { plan: business.plan.name })
              : $t('hubs.domain.notInPlan.heading')
          "
        >
          {{ $t('hubs.domain.notInPlan.body') }}
          <template
            v-if="plansWay"
            #actions
          >
            <WebOnly>
              <ion-button
                v-if="business.can.manage_billing"
                :router-link="toPlans"
                fill="outline"
                size="small"
                data-testid="domain-plans"
              >
                {{ $t('hubs.domain.notInPlan.plans') }}
              </ion-button>
              <template #app>
                <span>{{ $t('hubs.common.storeInBrowser') }}</span>
              </template>
            </WebOnly>
          </template>
        </InlineFeedback>

        <p
          v-else-if="available && !isOwner"
          class="ion-margin-top"
          data-testid="domain-owner-only"
        >
          {{ $t('hubs.domain.ownerOnly') }}
        </p>

        <form
          v-if="asks"
          class="ion-margin-top"
          novalidate
          data-testid="domain-form"
          @submit.prevent="connect"
        >
          <ion-input
            data-testid="domain-input"
            mode="md"
            fill="outline"
            label-placement="floating"
            inputmode="url"
            autocapitalize="off"
            autocomplete="off"
            :spellcheck="false"
            :label="$t('hubs.domain.field')"
            :placeholder="$t('hubs.domain.placeholder')"
            :value="typed"
            :disabled="request.pending.value"
            :error-text="errors.domain"
            :class="{ 'ion-invalid': !!errors.domain, 'ion-touched': !!errors.domain }"
            @ion-input="typed = value($event)"
          />
          <p>{{ $t('hubs.domain.fieldHint') }}</p>
          <InlineFeedback
            v-if="formError"
            tone="danger"
            class="ion-margin-top"
            data-testid="domain-form-error"
          >
            {{ formError }}
          </InlineFeedback>
          <ion-button
            class="ion-margin-top"
            data-testid="domain-connect"
            :disabled="!typed.trim() || request.pending.value"
            @click="connect"
          >
            <ion-spinner
              v-if="request.pending.value"
              slot="start"
              name="crescent"
              aria-hidden="true"
            />
            <HubIcon
              v-else
              slot="start"
              name="ion:globe-outline"
              aria-hidden="true"
            />
            {{ $t('hubs.domain.connect') }}
          </ion-button>
        </form>

        <ion-button
          v-if="domain && changes && domain.state !== 'removing'"
          class="ion-margin-top"
          data-testid="domain-remove"
          fill="outline"
          color="danger"
          @click="askToRemove"
        >
          <HubIcon
            slot="start"
            name="ion:trash-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.domain.remove') }}
        </ion-button>
      </template>
    </ion-card-content>
    <ConfirmDialog
      v-if="domain"
      v-model:open="confirming"
      testid="domain-remove-dialog"
      tone="danger"
      confirm-icon="ion:trash-outline"
      :title="$t('hubs.domain.removeTitle', { domain: domain.domain })"
      :message="$t('hubs.domain.removeMessage', { domain: domain.domain })"
      :confirm-label="$t('hubs.domain.remove')"
      :pending="remove.pending.value"
      :error="forDialog(remove.error.value)"
      @confirm="confirmRemove"
      @cancel="remove.error.value = null"
    />
  </ion-card>
</template>
