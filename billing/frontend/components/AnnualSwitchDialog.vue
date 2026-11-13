<script setup lang="ts">
// «Switch to annual» (or back to monthly) on the business's own plan (mockups `store.html` «modal-annual»):
// always for THE business chosen in the Store, never another's, with what
// it charges today WITH VAT (Stripe's prorated preview, `billing.checkout.start`), the new price, what it
// is a month, and that its modules follow the billing (Stripe bills one interval per subscription).
// Confirmed with `billing.plan.change` at the preview's proration date; a refusal stays in the dialog.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonItem, IonLabel, IonList, IonNote, IonSkeletonText } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../../../hubs/frontend/error-text';
import type { BillingInterval, PlanOut, SubscriptionOut } from '../../../frontend/sdk-types';
import { useChargePreview } from '../charge-preview';
import { formatCents, formatDate, formatEuros } from '../format';

const props = defineProps<{
  business: { id: string; name: string };
  /** The business's own plan. */
  plan: PlanOut | null;
  /** The billing it switches to. */
  interval: BillingInterval;
}>();

const open = defineModel<boolean>('open', { default: false });

const emit = defineEmits<{ done: [subscription: SubscriptionOut] }>();

const { t, locale } = useI18n();
const { forDialog } = useErrorText();
const charge = useChargePreview();
const change = useCommand('billing.plan.change');
const confirmError = shallowRef<FormModalError | null>(null);

const annual = computed(() => props.interval === 'year');
const periodName = computed(() => t(`billing.plans.periodName.${props.interval}`));
const money = (cents: number) => formatCents(cents, locale.value);
const error = computed(() => confirmError.value ?? (charge.state.value === 'error' ? forDialog(charge.error.value) : null));
/** Back to monthly waits for the end of the paid year, and a trial charges nothing until it ends: never «from now on» then. */
const intro = computed(() => {
  const params = { business: props.business.name, plan: props.plan?.name ?? '', period: periodName.value };
  const startsAt = charge.preview.value?.charge_starts_at;
  return startsAt
    ? t('billing.annual.introScheduled', { ...params, date: formatDate(startsAt, locale.value) })
    : t('billing.annual.intro', params);
});

async function loadPreview(): Promise<void> {
  if (!props.plan) return;
  await charge.load({ hub_id: props.business.id, plan: props.plan.slug, interval: props.interval });
}

watch(
  [open, () => props.plan, () => props.interval],
  ([isOpen, plan]) => {
    if (!isOpen || !plan) return;
    confirmError.value = null;
    void loadPreview();
  },
  { immediate: true },
);

async function confirm(): Promise<void> {
  const plan = props.plan;
  const preview = charge.preview.value;
  if (!plan || !preview || charge.state.value !== 'ready') return;
  confirmError.value = null;
  try {
    const subscription = await change.run({
      hub_id: props.business.id,
      plan: plan.slug,
      interval: props.interval,
      proration_date: preview.proration_date,
    });
    const params = { business: props.business.name, plan: plan.name, period: periodName.value };
    const waiting = subscription.scheduled_change;
    void toastSuccess(
      waiting
        ? t('billing.plans.switchScheduled', { ...params, date: formatDate(waiting.starts_at, locale.value) })
        : t('billing.plans.switched', params),
    );
    emit('done', subscription);
    open.value = false;
  } catch {
    if (change.error.value?.code === 'billing.preview_expired') {
      await loadPreview();
      confirmError.value = { message: t('billing.proration.expired'), code: 'billing.preview_expired' };
      return;
    }
    confirmError.value = forDialog(change.error.value);
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="annual-modal"
    :title="annual ? $t('billing.annual.title', { plan: plan?.name ?? '' }) : $t('billing.annual.titleMonthly', { plan: plan?.name ?? '' })"
    :submit-label="annual ? $t('billing.annual.confirm') : $t('billing.annual.confirmMonthly')"
    submit-icon="ion:calendar-outline"
    :submit-disabled="charge.state.value !== 'ready'"
    :pending="change.pending.value"
    :error="error"
    @submit="confirm"
  >
    <p
      class="charge-intro"
      data-testid="annual-intro"
    >
      {{ intro }}
    </p>
    <div
      v-if="charge.state.value === 'loading' || charge.state.value === 'idle'"
      class="charge-summary"
      :aria-label="$t('billing.proration.loading')"
      aria-busy="true"
    >
      <ion-skeleton-text
        v-for="row in 5"
        :key="row"
        animated
        class="charge-skeleton"
      />
    </div>
    <ion-button
      v-else-if="charge.state.value === 'error'"
      size="small"
      fill="outline"
      data-testid="annual-retry"
      @click="loadPreview"
    >
      <HubIcon
        slot="start"
        name="ion:refresh-outline"
        aria-hidden="true"
      />
      {{ $t('billing.store.retry') }}
    </ion-button>
    <template v-else-if="charge.preview.value && plan">
      <ion-list
        lines="none"
        class="charge-summary"
      >
        <ion-item
          class="charge-row"
          data-testid="annual-row"
        >
          <ion-label>{{ $t('billing.proration.today') }}</ion-label>
          <ion-note slot="end">
            {{ $t('billing.proration.netPlusVat', { amount: money(charge.netCents.value) }) }}
          </ion-note>
        </ion-item>
        <ion-item
          class="charge-row"
          data-testid="annual-row"
        >
          <ion-label>{{ $t('billing.proration.vat') }}</ion-label>
          <ion-note slot="end">
            {{ money(charge.preview.value.tax_cents) }}
          </ion-note>
        </ion-item>
        <ion-item
          class="charge-row is-total"
          data-testid="annual-row"
        >
          <ion-label>{{ $t('billing.annual.chargedToday') }}</ion-label>
          <ion-note slot="end">
            {{ money(charge.preview.value.amount_due_cents) }}
          </ion-note>
        </ion-item>
        <ion-item
          class="charge-row"
          data-testid="annual-row"
        >
          <ion-label>{{ annual ? $t('billing.annual.price', { plan: plan.name }) : $t('billing.annual.priceMonthly', { plan: plan.name }) }}</ion-label>
          <ion-note slot="end">
            {{
              annual
                ? $t('billing.modules.perYear', { price: formatEuros(plan.price_annual, locale) })
                : $t('billing.modules.perMonth', { price: formatEuros(plan.price_monthly, locale) })
            }}
          </ion-note>
        </ion-item>
        <ion-item
          v-if="annual"
          class="charge-row"
          data-testid="annual-row"
        >
          <ion-label>{{ $t('billing.annual.equivalent') }}</ion-label>
          <ion-note slot="end">
            {{ $t('billing.annual.perMonth', { price: formatEuros(Number(plan.price_annual) / 12, locale) }) }}
          </ion-note>
        </ion-item>
      </ion-list>
      <p
        class="charge-note"
        data-testid="annual-modules"
      >
        {{ $t('billing.annual.modules', { period: periodName }) }}
      </p>
    </template>
  </FormModal>
</template>

<style scoped src="./charge-summary.css"></style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
