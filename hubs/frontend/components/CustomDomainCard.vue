<script setup lang="ts">
// «Own domain» in a business's Settings (HUBS-F17): the public
// website of the business on a domain of its owner's, never the app. The live `hubs.custom_domain.get` says whether this
// deployment connects domains (`available`), whether the plan the business has now includes one (`in_plan`) and the
// domain it has; it follows the domain's changes and the plan's. The owner writes `www.…` and asks for it
// (`hubs.custom_domain.request`): the answer brings the two CNAME records to create at once, each with «Copy» — the
// validation one first, which stays for good, and the one that points to ERPlora once the certificate is ready. The
// state and where it is stuck are the server's words (`state_label`, `reason_label`); the hourly check, its last run
// and the failures that count towards the three in a row that stop serving it are said here. A domain that is not
// connected is asked for again (or another one) with the same form; removing it asks first
// (`hubs.custom_domain.remove`). A plan without it says so, names the first plan on sale that includes one and is not
// upgrade-only (read then from `hubs.plan.list`; without it, «a plan that includes one») and gives the way to
// the plans (the Store, only on the web and for whoever handles the billing), never a disabled form. Only the owner
// connects or removes it; an administrator reads it. Nothing is shown until the business is there: the query rides the
// page's first stream, and its loading, error and time-out are `useLiveState`'s.
import {
  ConfirmDialog,
  formatDateTime,
  InlineFeedback,
  type InlineFeedbackTone,
  StatusPill,
  type StatusPillTone,
} from '@erplora/ui/components';
import { HubIcon, toastSuccess, useSurface, WebOnly } from '@erplora/ui/shell';
import { fieldErrors, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonInput, IonSkeletonText, IonSpinner, IonText } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { STORE } from '../../../accounts/frontend/paths';
import { useLiveState } from '../../../frontend/live-state';
import LoadFailed from '../../../frontend/LoadFailed.vue';
import type { BusinessDetailOut } from '../../../frontend/sdk-types/hubs';
import type {
  CustomDomainReason,
  CustomDomainState,
  CustomDomainStatusOut,
} from '../../../frontend/sdk-types/hubs-custom-domains';
import { useErrorText } from '../error-text';
import CustomDomainRecords from './CustomDomainRecords.vue';

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

/** The plan of the notice: the first plan on sale that includes a custom domain and that any business can move to (an
 * upgrade-only one opens only from a paid plan), asked for only once a plan without one shows it; '' while it is read,
 * if it cannot be or if there is none, and the notice says «a plan that includes one». */
const client = useLiveClient();
const planWithIt = shallowRef('');
let plansAsked = false;
watch(
  () => available.value && !!status.value && !status.value.in_plan,
  async (outOfPlan) => {
    if (!outOfPlan || plansAsked) return;
    plansAsked = true;
    try {
      const { plans } = await client.api.call('hubs.plan.list');
      planWithIt.value = plans?.find((plan) => plan.includes_custom_domain && !plan.upgrade_only)?.name ?? '';
    } catch {
      // Without the plans on sale the notice still says what the plan lacks and leads to them.
    }
  },
  { immediate: true },
);

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
    toastSuccess(t('hubs.domain.connected', { domain: answer.domain }));
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
  toastSuccess(t('hubs.domain.removed', { domain: now.domain }));
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

          <CustomDomainRecords
            :domain="domain"
            @look-again="live.refresh()"
          />

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
          {{ planWithIt ? $t('hubs.domain.notInPlan.bodyNamed', { plan: planWithIt }) : $t('hubs.domain.notInPlan.body') }}
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
