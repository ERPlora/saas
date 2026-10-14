<script setup lang="ts">
// Adding a module to, or changing the plan of, a business Stripe bills already (PLAN-SAAS §3.2; mockups
// `store.html` «modal-confirm»; UX-AUDIT-4 W-F4: one dialog per module, with ITS proration): no checkout,
// an item of the business's subscription, charged now and prorated. It asks Stripe's preview first
// (`billing.checkout.start`) and says it to the cent — today without VAT, the VAT, the total, and what it
// costs from the renewal — then confirms with the preview's proration date (`billing.checkout.confirm` for
// a module, `billing.plan.change` for a plan), so the charge is the one shown. A refusal (a declined
// card, an unpaid invoice) stays in the dialog; an out-of-date price is asked again and said, never
// charged blind. A business that turns out not to pay yet goes to the checkout (`checkout`).
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonItem, IonLabel, IonList, IonNote, IonSkeletonText } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../../../hubs/frontend/error-text';
import type { BillingInterval, SubscriptionOut } from '../../../frontend/sdk-types';
import { useChargePreview } from '../charge-preview';
import { formatCents, formatDate } from '../format';

export type ProrationItem =
  | { kind: 'module'; slug: string; name: string; recurringCents: number; interval: BillingInterval }
  | { kind: 'plan'; slug: string; name: string; from: string; recurringCents: number; interval: BillingInterval };

const props = defineProps<{
  business: { id: string; name: string };
  item: ProrationItem | null;
  /** The business's next renewal: from then on the new price. */
  renewal: string | null;
  /** A promo code the owner typed in the Store (a plan only). */
  promoCode: string;
}>();

const open = defineModel<boolean>('open', { default: false });

const emit = defineEmits<{
  /** Done: the subscription as Stripe left it. */
  done: [subscription: SubscriptionOut];
  /** The business does not pay yet: it buys in the Embedded Checkout instead. */
  checkout: [];
}>();

const { t, locale } = useI18n();
const { forDialog } = useErrorText();
const charge = useChargePreview();
const confirmModule = useCommand('billing.checkout.confirm');
const changePlan = useCommand('billing.plan.change');
const confirmError = shallowRef<FormModalError | null>(null);

const money = (cents: number) => formatCents(cents, locale.value);
const pending = computed(() => confirmModule.pending.value || changePlan.pending.value);
const error = computed(() => confirmError.value ?? (charge.state.value === 'error' ? forDialog(charge.error.value) : null));

const title = computed(() => {
  const item = props.item;
  if (!item) return '';
  return item.kind === 'module'
    ? t('billing.proration.titleModule', { module: item.name })
    : t('billing.proration.titlePlan', { plan: item.name });
});
const intro = computed(() => {
  const item = props.item;
  if (!item) return '';
  return item.kind === 'module'
    ? t('billing.proration.intoModule', { business: props.business.name })
    : t('billing.proration.intoPlan', { business: props.business.name, from: item.from, plan: item.name });
});
const recurring = computed(() => {
  const item = props.item;
  if (!item) return '';
  const price = money(item.recurringCents);
  return item.interval === 'year' ? t('billing.modules.perYear', { price }) : t('billing.modules.perMonth', { price });
});
const submitLabel = computed(() => {
  const due = charge.preview.value?.amount_due_cents ?? 0;
  const isModule = props.item?.kind === 'module';
  if (!due) return isModule ? t('billing.proration.add') : t('billing.proration.change');
  return isModule
    ? t('billing.proration.payAndAdd', { amount: money(due) })
    : t('billing.proration.payAndChange', { amount: money(due) });
});

function startInput() {
  const item = props.item!;
  return item.kind === 'module'
    ? { hub_id: props.business.id, module: item.slug }
    : { hub_id: props.business.id, plan: item.slug, interval: item.interval, promo_code: props.promoCode };
}

async function loadPreview(): Promise<void> {
  if (!props.item) return;
  await charge.load(startInput());
  if (charge.state.value === 'checkout') {
    emit('checkout');
    open.value = false;
  }
}

watch(
  [open, () => props.item],
  ([isOpen, item]) => {
    if (!isOpen || !item) return;
    confirmError.value = null;
    void loadPreview();
  },
  { immediate: true },
);

async function confirm(): Promise<void> {
  const item = props.item;
  const preview = charge.preview.value;
  if (!item || !preview || charge.state.value !== 'ready') return;
  confirmError.value = null;
  const command = item.kind === 'module' ? confirmModule : changePlan;
  try {
    const subscription =
      item.kind === 'module'
        ? await confirmModule.run({ hub_id: props.business.id, module: item.slug, proration_date: preview.proration_date })
        : await changePlan.run({
            hub_id: props.business.id,
            plan: item.slug,
            interval: item.interval,
            proration_date: preview.proration_date,
            promo_code: props.promoCode,
          });
    void toastSuccess(
      item.kind === 'module'
        ? t('billing.modules.added', { module: item.name, business: props.business.name })
        : t('billing.plans.changed', { business: props.business.name, plan: item.name }),
    );
    emit('done', subscription);
    open.value = false;
  } catch {
    if (command.error.value?.code === 'billing.preview_expired') {
      await loadPreview();
      confirmError.value = { message: t('billing.proration.expired'), code: 'billing.preview_expired' };
      return;
    }
    confirmError.value = forDialog(command.error.value);
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="proration-modal"
    :title="title"
    :submit-label="submitLabel"
    submit-icon="ion:checkmark-outline"
    :submit-disabled="charge.state.value !== 'ready'"
    :pending="pending"
    :error="error"
    @submit="confirm"
  >
    <p
      class="charge-intro"
      data-testid="proration-intro"
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
        v-for="row in 4"
        :key="row"
        animated
        class="charge-skeleton"
      />
    </div>
    <ion-button
      v-else-if="charge.state.value === 'error'"
      size="small"
      fill="outline"
      data-testid="proration-retry"
      @click="loadPreview"
    >
      <HubIcon
        slot="start"
        name="ion:refresh-outline"
      />
      {{ $t('billing.store.retry') }}
    </ion-button>
    <template v-else-if="charge.preview.value">
      <p
        v-if="charge.preview.value.charge_starts_at"
        class="charge-note"
        data-testid="proration-trial"
      >
        {{ $t('billing.proration.trial', { date: formatDate(charge.preview.value.charge_starts_at, locale) }) }}
      </p>
      <ion-list
        v-else
        lines="none"
        class="charge-summary"
      >
        <ion-item
          class="charge-row"
          data-testid="proration-row"
        >
          <ion-label>{{ $t('billing.proration.today') }}</ion-label>
          <ion-note slot="end">
            {{ $t('billing.proration.netPlusVat', { amount: money(charge.netCents.value) }) }}
          </ion-note>
        </ion-item>
        <ion-item
          class="charge-row"
          data-testid="proration-row"
        >
          <ion-label>{{ $t('billing.proration.vat') }}</ion-label>
          <ion-note slot="end">
            {{ money(charge.preview.value.tax_cents) }}
          </ion-note>
        </ion-item>
        <ion-item
          class="charge-row is-total"
          data-testid="proration-row"
        >
          <ion-label>{{ $t('billing.proration.total') }}</ion-label>
          <ion-note slot="end">
            {{ money(charge.preview.value.amount_due_cents) }}
          </ion-note>
        </ion-item>
        <ion-item
          class="charge-row"
          data-testid="proration-row"
        >
          <ion-label>{{ renewal ? $t('billing.proration.from', { date: formatDate(renewal, locale) }) : $t('billing.proration.recurring') }}</ion-label>
          <ion-note slot="end">
            {{ recurring }}
          </ion-note>
        </ion-item>
      </ion-list>
      <p class="charge-note">
        {{ item?.kind === 'module' ? $t('billing.proration.moduleNote') : $t('billing.proration.planNote') }}
      </p>
    </template>
  </FormModal>
</template>

<style scoped src="./charge-summary.css"></style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
