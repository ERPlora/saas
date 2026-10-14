<script setup lang="ts">
// «Edit details» of the billing details (mockups `billing.html` «modal-profile», «profile-invalid»; README §3b
// and §4; PLAN-SAAS §3.1): who ERPlora invoices for the businesses this payer pays — the Store's
// BillingDetailsForm in a FormModal, plus which business «use the business’s name and country» copies from
// when it pays several. The tax ID is checked in VIES as it is typed, after a pause (`billing.vat_check.run`;
// a current proof is reused, so asking costs nothing): the verdict says what the invoice will do, and a
// malformed one is the field's error. Saved with `hubs.billing_profile.update` (VIES again on the server);
// a 422 puts each message under its field. Fiscal data is not selling: it shows on every surface (README §4).
import { FormModal } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, onScopeDispose, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../../../hubs/frontend/error-text';
import type { BillingProfileOut, InvoiceBusinessOut, VatCheckOut } from '../../../frontend/sdk-types';
import BillingDetailsForm, { type BillingDetailsDraft } from './BillingDetailsForm.vue';

const props = defineProps<{
  /** The businesses this payer pays (the first one names the payer to the server). */
  businesses: InvoiceBusinessOut[];
  profile: BillingProfileOut;
}>();

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ saved: [profile: BillingProfileOut] }>();

/** The pause after typing before the tax ID is asked to VIES. */
const VIES_PAUSE_MS = 800;
/** Shorter than this is not a tax ID yet. */
const MIN_TAX_ID = 8;

const { t } = useI18n();
const { forDialog } = useErrorText();
const client = useLiveClient();
const save = useCommand('hubs.billing_profile.update');

const draft = shallowRef<BillingDetailsDraft>(fromProfile(props.profile));
const hubId = shallowRef(props.profile.hub_id);
const payers = computed(() => props.businesses.filter((business): business is { id: string; name: string } => !!business.id));

function fromProfile(profile: BillingProfileOut): BillingDetailsDraft {
  return {
    billing_name: profile.billing_name,
    tax_id: profile.tax_id,
    billing_address: profile.billing_address,
    billing_city: profile.billing_city,
    billing_postal_code: profile.billing_postal_code,
    billing_country: profile.billing_country,
    billing_email: profile.billing_email,
    same_as_business: profile.same_as_business,
  };
}

// ── VIES ────────────────────────────────────────────────────────────────────────────────────────
type Vies = { state: 'checking' } | { state: 'done'; verdict: VatCheckOut };
const vies = shallowRef<Vies | null>(null);
const viesError = shallowRef('');
let pending: (() => void) | null = null;
let asked = 0;

const tidy = (value: string) => value.replace(/[\s.-]/g, '').toUpperCase();

async function check(number: string): Promise<void> {
  const mine = ++asked;
  vies.value = { state: 'checking' };
  try {
    const verdict = await client.api.call('billing.vat_check.run', { vat_number: number, country: draft.value.billing_country || '' });
    if (mine === asked) vies.value = { state: 'done', verdict };
  } catch (error) {
    if (mine !== asked) return;
    vies.value = null;
    const field = error instanceof ApiError ? error.fields?.vat_number : undefined;
    if (field) viesError.value = field;
    else console.warn('billing: the tax ID could not be checked in VIES now', error);
  }
}

function askLater(value: string): void {
  pending?.();
  pending = null;
  asked += 1;
  viesError.value = '';
  const number = tidy(value);
  if (number.length < MIN_TAX_ID) {
    vies.value = null;
    return;
  }
  vies.value = { state: 'checking' };
  pending = client.schedule(() => {
    pending = null;
    void check(number);
  }, VIES_PAUSE_MS);
}
onScopeDispose(() => pending?.());

watch(
  () => draft.value.tax_id,
  (now, before) => {
    if (open.value && now !== before) askLater(now);
  },
);

const viesText = computed(() => {
  const now = vies.value;
  if (!now) return '';
  if (now.state === 'checking') return t('billing.payment.vies.checking');
  const { status, name } = now.verdict;
  if (status === 'verified') return name ? t('billing.payment.vies.verified', { name }) : t('billing.payment.vies.verifiedNoName');
  return t(`billing.payment.vies.${status}`);
});
const viesOk = computed(() => vies.value?.state === 'done' && ['verified', 'national'].includes(vies.value.verdict.status));

// ── Opening and saving ──────────────────────────────────────────────────────────────────────────
watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    pending?.();
    pending = null;
    draft.value = fromProfile(props.profile);
    hubId.value = props.profile.hub_id;
    save.error.value = null;
    viesError.value = '';
    vies.value = null;
    const number = tidy(props.profile.tax_id);
    if (number.length >= MIN_TAX_ID) void check(number);
  },
  { immediate: true },
);

const fieldErrors = computed<Record<string, string>>(() => ({
  ...(save.error.value?.fields ?? {}),
  ...(viesError.value ? { tax_id: viesError.value } : {}),
}));

async function submit(): Promise<void> {
  try {
    const saved = await save.run({ hub_id: hubId.value, ...draft.value });
    void toastSuccess(t('billing.payment.modal.saved'));
    emit('saved', saved);
    open.value = false;
  } catch {
    // `save.error`: the dialog says it, each field its own.
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="billing-profile"
    :title="$t('billing.payment.modal.title')"
    :submit-label="$t('billing.payment.modal.save')"
    submit-icon="lucide:save"
    :pending="save.pending.value"
    :error="forDialog(save.error.value)"
    @submit="submit"
  >
    <div class="profile-form">
      <BillingDetailsForm
        v-model="draft"
        :field-errors="fieldErrors"
      />
      <ion-select
        v-if="draft.same_as_business && payers.length > 1"
        mode="md"
        fill="outline"
        interface="popover"
        label-placement="floating"
        data-testid="billing-profile-business"
        :label="$t('billing.payment.modal.copyFrom')"
        :helper-text="$t('billing.payment.modal.copyFromHint')"
        :value="hubId"
        @ion-change="hubId = String($event.detail.value)"
      >
        <ion-select-option
          v-for="business in payers"
          :key="business.id"
          :value="business.id"
        >
          {{ business.name }}
        </ion-select-option>
      </ion-select>
      <p
        v-if="viesText"
        class="vies-status"
        :class="{ 'is-ok': viesOk }"
        role="status"
        data-testid="vies-status"
      >
        {{ viesText }}
      </p>
      <p
        class="profile-note"
        data-testid="billing-profile-note"
      >
        {{ $t('billing.payment.modal.note') }}
      </p>
    </div>
  </FormModal>
</template>

<style scoped>
.profile-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.vies-status {
  margin: -4px 2px 0;
  font-size: 0.85rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 70%, transparent));
}
.vies-status.is-ok {
  color: var(--ep-success-text, var(--ion-color-success));
}
.profile-note {
  margin: 0;
  font-size: 0.82rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
</style>
