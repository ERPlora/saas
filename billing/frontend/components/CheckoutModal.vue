<script setup lang="ts">
// Buying for a business Stripe does not bill yet (PLAN-SAAS §3.2 and §4; mockups `store.html`
// «modal-checkout»; UX-AUDIT-4 W-06, X-02, X-09): Stripe's Embedded Checkout inside our own dialog.
//   1. Who pays (`hubs.billing_profile.get`): without a name, a country and a postal code — or when the
//      payer is another account's (after a transfer) — the form comes first and is saved
//      (`hubs.billing_profile.update`, VIES included); otherwise «Invoice to … · Change».
//   2. `billing.checkout.start` — the plan at the billing chosen (with the promo code typed) or the module,
//      named in the title — gives a Checkout Session's `client_secret`. Stripe.js (web only, loaded now:
//      `stripe-js.ts`) mounts it with `createEmbeddedCheckoutPage({ fetchClientSecret })` in the dialog.
//      A place the tax cannot be worked out for sends back to the form with the server's reason.
//   3. Stripe's `onComplete` → «Paying…», the checkout is destroyed, a toast says what happened and the
//      page goes to the business (the webhook applies the plan; Stripe's `return_url` is that page too).
// Every failure is said, with «Retry» (saas#1565: a silent spinner is the most expensive failure).
// Closing the dialog destroys the checkout (Stripe allows one at a time). The declined card is never
// offered: the checkout always asks for a card, and the dialog says why when the same payer's was declined.
// Off the web nothing starts: the apps sell nothing (round 17 §2.6).
import { FormModal, type FormModalError, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { HubIcon, toastSuccess, useSurface } from '@erplora/ui/shell';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonItem, IonLabel, IonSpinner } from '@ionic/vue';
import { computed, nextTick, onBeforeUnmount, shallowRef, useTemplateRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { useErrorText } from '../../../hubs/frontend/error-text';
import type { BillingInterval, BillingProfileOut } from '../../../frontend/sdk-types';
import { type EmbeddedCheckout, loadStripeJs } from '../stripe-js';
import BillingDetailsForm, { type BillingDetailsDraft } from './BillingDetailsForm.vue';

export interface CheckoutPurchase {
  kind: 'plan' | 'module';
  slug: string;
  name: string;
  interval: BillingInterval;
}

const props = defineProps<{
  business: { id: string; name: string };
  purchase: CheckoutPurchase | null;
  /** A promo code the owner typed in the Store (a plan only). */
  promoCode: string;
  /** The business whose card (the same payer's) the bank declined: the checkout asks for another (audit 2 R-21). */
  declinedFor?: string | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const emit = defineEmits<{
  /** The business pays already: the Store asks the price again and confirms it with its proration. */
  stale: [];
}>();

/** Where the server sends a sale it cannot tax: the payer's details answer it. */
const DETAILS_CODES = new Set([
  'billing.billing_location_required',
  'billing.tax_id_required',
  'billing.payer_required',
  'billing.uk_business_required',
]);

type Step = 'loading' | 'details' | 'pay';
type PayState = 'mounting' | 'mounted' | 'completing' | 'error';

const { t } = useI18n();
const { text, forDialog } = useErrorText();
const { isWeb } = useSurface();
const client = useLiveClient();
const router = useRouter();
const start = useCommand('billing.checkout.start');
const saveProfile = useCommand('hubs.billing_profile.update');

const step = shallowRef<Step>('loading');
const payState = shallowRef<PayState>('mounting');
const profile = shallowRef<BillingProfileOut | null>(null);
const draft = shallowRef<BillingDetailsDraft>(emptyDraft());
const dialogError = shallowRef<FormModalError | null>(null);
const payError = shallowRef('');
const stripeArea = useTemplateRef<HTMLElement>('stripeArea');
let checkout: EmbeddedCheckout | null = null;
/** Bumped on every opening and every closing: a late answer of an earlier attempt is dropped. */
let attempt = 0;

function emptyDraft(): BillingDetailsDraft {
  return {
    billing_name: '',
    tax_id: '',
    billing_address: '',
    billing_city: '',
    billing_postal_code: '',
    billing_country: '',
    billing_email: '',
    same_as_business: false,
  };
}

const title = computed(() => {
  const purchase = props.purchase;
  if (!purchase) return '';
  return purchase.kind === 'plan'
    ? t('billing.checkout.titlePlan', { plan: purchase.name })
    : t('billing.checkout.titleModule', { module: purchase.name });
});
const period = computed(() => t(`billing.checkout.period.${props.purchase?.interval ?? 'month'}`));
const invoiceTo = computed(() => {
  const payer = profile.value;
  if (!payer) return '';
  return [payer.billing_name, payer.tax_id].filter(Boolean).join(' · ');
});
const detailsComplete = computed(() => {
  const d = draft.value;
  const named = d.same_as_business || (!!d.billing_name.trim() && !!d.billing_country);
  return named && !!d.billing_postal_code.trim();
});

function needsDetails(payer: BillingProfileOut): boolean {
  return payer.paid_by_another_account || !payer.billing_name || !payer.billing_country || !payer.billing_postal_code;
}

function letCheckoutGo(): void {
  const current = checkout;
  checkout = null;
  try {
    current?.destroy();
  } catch (error) {
    console.error('billing: the Embedded Checkout could not be destroyed', error);
  }
}

async function begin(): Promise<void> {
  const mine = ++attempt;
  letCheckoutGo();
  dialogError.value = null;
  payError.value = '';
  step.value = 'loading';
  try {
    const payer = await client.api.call('hubs.billing_profile.get', { hub_id: props.business.id });
    if (mine !== attempt) return;
    profile.value = payer;
    draft.value = { ...emptyDraft(), ...pickDraft(payer) };
    if (needsDetails(payer)) step.value = 'details';
    else await pay(mine);
  } catch (error) {
    if (mine !== attempt) return;
    step.value = 'pay';
    payState.value = 'error';
    payError.value = text(error as never);
  }
}

function pickDraft(payer: BillingProfileOut): BillingDetailsDraft {
  return {
    billing_name: payer.billing_name,
    tax_id: payer.tax_id,
    billing_address: payer.billing_address,
    billing_city: payer.billing_city,
    billing_postal_code: payer.billing_postal_code,
    billing_country: payer.billing_country,
    billing_email: payer.billing_email,
    same_as_business: payer.same_as_business,
  };
}

async function pay(mine = attempt): Promise<void> {
  const purchase = props.purchase;
  if (!purchase) return;
  step.value = 'pay';
  payState.value = 'mounting';
  payError.value = '';
  let session;
  try {
    session = await start.run(
      purchase.kind === 'plan'
        ? { hub_id: props.business.id, plan: purchase.slug, interval: purchase.interval, promo_code: props.promoCode }
        : { hub_id: props.business.id, module: purchase.slug, interval: purchase.interval },
    );
  } catch {
    if (mine !== attempt) return;
    const failure = start.error.value;
    if (failure && DETAILS_CODES.has(failure.code)) {
      step.value = 'details';
      dialogError.value = forDialog(failure);
      return;
    }
    payState.value = 'error';
    payError.value = text(failure);
    return;
  }
  if (mine !== attempt) return;
  if (session.flow !== 'checkout' || !session.client_secret || !session.publishable_key) {
    emit('stale');
    open.value = false;
    return;
  }
  const secret = session.client_secret;
  try {
    const Stripe = await loadStripeJs();
    const mounted = await Stripe(session.publishable_key).createEmbeddedCheckoutPage({
      fetchClientSecret: () => Promise.resolve(secret),
      onComplete: () => void complete(),
    });
    if (mine !== attempt) {
      mounted.destroy();
      return;
    }
    checkout = mounted;
    await nextTick();
    if (!stripeArea.value) throw new Error('billing: the checkout has nowhere to mount');
    mounted.mount(stripeArea.value);
    payState.value = 'mounted';
  } catch (error) {
    if (mine !== attempt) return;
    console.error('billing: the Embedded Checkout could not be mounted', error);
    letCheckoutGo();
    payState.value = 'error';
    payError.value = '';
  }
}

async function complete(): Promise<void> {
  const purchase = props.purchase;
  payState.value = 'completing';
  letCheckoutGo();
  if (!purchase) return;
  void toastSuccess(
    purchase.kind === 'plan'
      ? t('billing.checkout.plan', { business: props.business.name, plan: purchase.name })
      : t('billing.checkout.module', { module: purchase.name, business: props.business.name }),
  );
  // «Paying…» stays on screen until the business's page takes over.
  await router.push(`/businesses/${props.business.id}/summary`);
  attempt += 1;
  open.value = false;
}

async function saveDetails(): Promise<void> {
  if (!detailsComplete.value) return;
  dialogError.value = null;
  try {
    profile.value = await saveProfile.run({ hub_id: props.business.id, ...draft.value });
  } catch {
    dialogError.value = forDialog(saveProfile.error.value);
    return;
  }
  await pay();
}

function changeDetails(): void {
  attempt += 1;
  letCheckoutGo();
  dialogError.value = null;
  step.value = 'details';
}

watch(
  open,
  (isOpen) => {
    if (isOpen && isWeb.value && props.purchase) {
      void begin();
      return;
    }
    attempt += 1;
    letCheckoutGo();
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  attempt += 1;
  letCheckoutGo();
});
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="checkout-modal"
    :title="title"
    :submit-label="$t('billing.details.continue')"
    submit-icon="ion:lock-closed-outline"
    :submit-disabled="!detailsComplete"
    :pending="saveProfile.pending.value"
    :error="step === 'details' ? dialogError : null"
    @submit="saveDetails"
  >
    <p
      class="checkout-for"
      data-testid="checkout-for"
    >
      {{ $t('billing.checkout.forBusiness', { business: business.name, period }) }}
    </p>

    <div
      v-if="step === 'loading'"
      class="checkout-loading"
      role="status"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('billing.checkout.loading') }}
    </div>

    <template v-else-if="step === 'details'">
      <InlineFeedback
        v-if="profile?.paid_by_another_account"
        tone="warning"
        data-testid="checkout-another-account"
      >
        {{ $t('billing.details.anotherAccount') }}
      </InlineFeedback>
      <BillingDetailsForm
        v-model="draft"
        :field-errors="dialogError?.fields ?? {}"
      />
    </template>

    <template v-else>
      <ion-item
        v-if="invoiceTo"
        lines="none"
        class="checkout-invoice-to"
        data-testid="checkout-invoice-to"
      >
        <ion-label class="ion-text-wrap">
          <p class="checkout-muted">
            {{ $t('billing.checkout.invoiceTo') }}
          </p>
          {{ invoiceTo }}
        </ion-label>
        <ion-button
          slot="end"
          fill="clear"
          size="small"
          data-testid="checkout-change-details"
          @click="changeDetails"
        >
          <HubIcon
            slot="start"
            name="ion:create-outline"
            aria-hidden="true"
          />
          {{ $t('billing.checkout.change') }}
        </ion-button>
      </ion-item>
      <InlineFeedback
        v-if="declinedFor"
        tone="warning"
        icon="ion:card-outline"
        data-testid="checkout-declined"
      >
        {{ $t('billing.checkout.declined', { name: declinedFor }) }}
      </InlineFeedback>
      <div class="checkout-stripe">
        <span class="checkout-secure">
          <HubIcon
            name="ion:lock-closed-outline"
            aria-hidden="true"
          />
          {{ $t('billing.checkout.secure') }}
        </span>
        <InlineFeedback
          v-if="payState === 'error'"
          tone="danger"
          :heading="$t('billing.checkout.loadError')"
          data-testid="checkout-error"
        >
          {{ payError || $t('billing.checkout.loadErrorBody') }}
          <template #actions>
            <ion-button
              size="small"
              fill="outline"
              data-testid="checkout-retry"
              @click="begin"
            >
              <HubIcon
                slot="start"
                name="ion:refresh-outline"
                aria-hidden="true"
              />
              {{ $t('billing.checkout.retry') }}
            </ion-button>
          </template>
        </InlineFeedback>
        <div
          v-else-if="payState === 'mounting'"
          class="checkout-loading"
          role="status"
        >
          <ion-spinner
            name="crescent"
            aria-hidden="true"
          />
          {{ $t('billing.checkout.loading') }}
        </div>
        <p
          v-else-if="payState === 'completing'"
          class="checkout-paying"
          role="status"
        >
          <StatusPill
            tone="info"
            busy
            :label="$t('billing.checkout.paying')"
            data-testid="checkout-paying"
          />
        </p>
        <div
          v-show="payState === 'mounted' || payState === 'mounting'"
          ref="stripeArea"
          class="checkout-stripe__mount"
          data-testid="checkout-stripe"
        />
      </div>
      <p class="checkout-muted checkout-terms">
        {{ $t('billing.checkout.terms') }}
      </p>
    </template>

    <template
      v-if="step !== 'details'"
      #footer
    >
      <span />
    </template>
  </FormModal>
</template>

<style scoped>
.checkout-for {
  margin: 0 0 12px;
  font-size: 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.checkout-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 0;
  font-size: 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.checkout-invoice-to {
  --background: transparent;
  --padding-start: 12px;
  --inner-padding-end: 4px;
  --min-height: 0;
  margin-bottom: 12px;
  border: 1px solid var(--ion-border-color);
  border-radius: var(--ep-radius-sm, 10px);
  font-size: 0.9rem;
}
.checkout-invoice-to ion-label {
  margin: 8px 0;
  color: var(--ion-text-color);
}
.checkout-invoice-to .checkout-muted {
  margin: 0 0 2px;
}
.checkout-muted {
  font-size: 0.82rem;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.checkout-stripe {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}
.checkout-secure {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82rem;
  font-weight: 600;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.checkout-stripe__mount {
  min-height: 0;
}
.checkout-paying {
  margin: 8px 0;
}
.checkout-terms {
  margin: 12px 0 0;
}
</style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
