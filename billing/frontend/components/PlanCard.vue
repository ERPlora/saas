<script setup lang="ts">
// A plan of the Store (mockups `store.html` «Planes»; round 17 §2.11; UX-AUDIT-4 X-03, X-08, X-09, X-14):
// its name, description, net price (monthly or annual, as the switch above says), features, the apps it turns
// on at once (`max_apps`, the cap the Hub applies since hub#256; 0 = all), the messages a month it includes
// (assistant and WhatsApp, PLAN-SAAS §3.6; 0 = none, no line) and its trial, in the order of /pricing/'s cards
// (public/pricing.py `plan_card`), and the ONE thing the chosen business can do with it now. What each button does is the page's: the card only
// says which one applies and emits it.
//   - On Free: «Upgrade to …» (Embedded Checkout), at the billing of the switch; the plan it is trying
//     says until when, and that buying it keeps the days left.
//   - Paying: «Change to …» (confirmed with its proration), «Switch to annual/monthly» on its own plan
//     when the switch shows the other billing, «Downgrade to Free» (cancels at the end of the period).
//   - Cancelled: «Keep the plan» on its plan; Free says from when; another plan waits for it.
//   - An unpaid invoice disables what charges, with the reason under the button (`aria-describedby`).
//     Cancelling is never blocked: it only stops the next charges.
import { StatusPill } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';
import { computed, useId } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BillingInterval, PlanOut, StoreSubscriptionOut } from '../../../frontend/sdk-types';
import { formatDate, formatEuros } from '../format';
import { type Block, isFree } from '../store';

const props = defineProps<{
  plan: PlanOut;
  /** The billing the switch above shows. */
  period: BillingInterval;
  /** The chosen business's plan (`billing.store.catalog`); none = Free. */
  subscription: StoreSubscriptionOut | null;
  /** An unpaid invoice of the business: nothing that charges. */
  block: Block | null;
}>();

const emit = defineEmits<{
  /** Buy it in the Embedded Checkout (a business Stripe does not bill yet). */
  upgrade: [period: BillingInterval];
  /** Move a paying business to it, confirmed with the proration. */
  change: [period: BillingInterval];
  /** Move its own plan to the other billing. */
  switch: [period: BillingInterval];
  /** Cancel the paid plan: the business goes to Free at the end of the period. */
  downgrade: [];
  /** Undo the cancellation. */
  keep: [];
}>();

type Action = 'upgrade' | 'change' | 'switch' | 'downgrade' | 'keep';

const { t, locale } = useI18n();
const hintId = `plan-hint-${useId()}`;

const free = computed(() => isFree(props.plan));
const paying = computed(() => !!props.subscription?.paying);
const current = computed(() => (props.subscription ? props.subscription.plan === props.plan.slug : free.value));
const cancelling = computed(() => paying.value && !!props.subscription?.cancel_at_period_end);
const periodEnd = computed(() => formatDate(props.subscription?.current_period_end, locale.value));
const trying = computed(() => {
  const subscription = props.subscription;
  if (!subscription || paying.value || subscription.trial_plan !== props.plan.slug || !subscription.trial_end) return false;
  return Date.parse(subscription.trial_end) > Date.now();
});

/** The one button of the card, whether it works now, and why not. */
const action = computed<{ kind: Action; disabled: boolean; hint: string } | null>(() => {
  const payFirst = props.block ? t('billing.plans.payFirst') : '';
  if (free.value) {
    if (current.value || !paying.value || cancelling.value) return null;
    return { kind: 'downgrade', disabled: false, hint: '' };
  }
  if (current.value && paying.value) {
    if (cancelling.value) return { kind: 'keep', disabled: !!props.block, hint: payFirst };
    if (props.period !== props.subscription?.billing_interval) return { kind: 'switch', disabled: !!props.block, hint: payFirst };
    return null;
  }
  if (paying.value) {
    if (cancelling.value) return { kind: 'change', disabled: true, hint: t('billing.plans.keepFirst') };
    return { kind: 'change', disabled: !!props.block, hint: payFirst };
  }
  return { kind: 'upgrade', disabled: !!props.block, hint: payFirst };
});

const label = computed(() => {
  const name = props.plan.name;
  switch (action.value?.kind) {
    case 'upgrade':
      return t('billing.plans.upgrade', { plan: name });
    case 'change':
      return t('billing.plans.change', { plan: name });
    case 'switch':
      return props.period === 'year'
        ? t('billing.plans.switchAnnual', { price: formatEuros(props.plan.price_annual, locale.value) })
        : t('billing.plans.switchMonthly', { price: formatEuros(props.plan.price_monthly, locale.value) });
    case 'downgrade':
      return t('billing.plans.downgrade');
    case 'keep':
      return t('billing.plans.keep');
    default:
      return '';
  }
});

const ICONS: Record<Action, string> = {
  upgrade: 'ion:sparkles-outline',
  change: 'ion:swap-vertical-outline',
  switch: 'ion:calendar-outline',
  downgrade: 'ion:arrow-down-outline',
  keep: 'ion:refresh-outline',
};

const price = computed(() => {
  if (free.value) return { amount: formatEuros(0, locale.value), suffix: t('billing.plans.forever') };
  if (props.period === 'year') {
    return {
      amount: formatEuros(props.plan.price_annual, locale.value),
      suffix: t('billing.plans.perYear', { monthly: formatEuros(Number(props.plan.price_annual) / 12, locale.value) }),
    };
  }
  return { amount: formatEuros(props.plan.price_monthly, locale.value), suffix: t('billing.plans.perMonth') };
});

type Line = { kind: 'feature' | 'apps' | 'quota'; text: string };

/** The features that say what a plan includes, in the languages its rows are written in (as /pricing/'s
 * `INCLUDES_LINES` and `INCLUDES_PREFIXES`): the apps it turns on at once go right after the first of them. */
const INCLUDES_LINES = new Set(['All apps included', 'Todas las apps incluidas']);
const INCLUDES_PREFIXES = ['Everything in ', 'Todo lo del plan '];
const saysWhatItIncludes = (feature: string) => INCLUDES_LINES.has(feature) || INCLUDES_PREFIXES.some((prefix) => feature.startsWith(prefix));

/** The lines of the card, as /pricing/ paints them: the plan's own features with the apps it turns on at once
 * right after what it includes (else at their end), the messages a month (a quota of 0 is none: no line) and,
 * last, its trial, the line `hubs.plan.list` ends a signable plan's features with. */
const lines = computed<Line[]>(() => {
  const plan = props.plan;
  const own = [...plan.features];
  const trial = !plan.upgrade_only && plan.trial_period_days > 0 && own.length > 0 ? own.splice(-1) : [];
  const apps = plan.max_apps > 0 ? t('billing.plans.appsAtOnce', { count: plan.max_apps }, plan.max_apps) : t('billing.plans.allAppsAtOnce');
  const at = own.findIndex(saysWhatItIncludes) + 1 || own.length;
  const feature = (text: string): Line => ({ kind: 'feature', text });
  const result: Line[] = [...own.slice(0, at).map(feature), { kind: 'apps', text: apps }, ...own.slice(at).map(feature)];
  const assistant = plan.assistant_messages_per_month;
  const whatsapp = plan.whatsapp_messages_per_month;
  if (assistant > 0) result.push({ kind: 'quota', text: t('billing.plans.assistantMessages', { count: assistant }, assistant) });
  if (whatsapp > 0) result.push({ kind: 'quota', text: t('billing.plans.whatsappMessages', { count: whatsapp }, whatsapp) });
  return [...result, ...trial.map(feature)];
});

/** What the card says under the features: a cancellation, Free's date, a trial's days. */
const note = computed(() => {
  if (current.value && cancelling.value && !free.value) {
    return t('billing.plans.cancelled', { plan: props.plan.name, date: periodEnd.value });
  }
  if (free.value && cancelling.value) return t('billing.plans.freeFrom', { date: periodEnd.value });
  if (trying.value) return t('billing.plans.trialKeeps');
  return '';
});

function run(): void {
  const kind = action.value?.kind;
  if (!kind || action.value?.disabled) return;
  if (kind === 'downgrade') emit('downgrade');
  else if (kind === 'keep') emit('keep');
  else if (kind === 'upgrade') emit('upgrade', props.period);
  else if (kind === 'change') emit('change', props.period);
  else emit('switch', props.period);
}
</script>

<template>
  <ion-card
    class="plan-card"
    :class="{ 'is-current': current }"
    :data-testid="`plan-${plan.slug}`"
  >
    <ion-card-content class="ion-padding plan-card__content">
      <div class="plan-card__head">
        <h2
          class="card-title"
          data-testid="plan-name"
        >
          {{ plan.name }}
        </h2>
        <StatusPill
          v-if="current"
          tone="info"
          :dot="false"
          :label="$t('billing.plans.current')"
          data-testid="plan-current"
        />
        <StatusPill
          v-if="trying"
          tone="info"
          :label="$t('billing.plans.trial', { date: formatDate(subscription?.trial_end, locale) })"
          data-testid="plan-trial"
        />
        <StatusPill
          v-if="plan.featured_label"
          tone="success"
          :dot="false"
          :label="plan.featured_label"
        />
      </div>
      <p
        v-if="plan.description"
        class="card-text"
      >
        {{ plan.description }}
      </p>
      <div
        class="plan-card__price"
        data-testid="plan-price"
      >
        {{ price.amount }} <small>{{ price.suffix }}</small>
      </div>
      <ion-list
        lines="none"
        class="plan-card__features"
      >
        <ion-item
          v-for="(line, index) in lines"
          :key="index"
          :data-testid="`plan-${line.kind}`"
        >
          <HubIcon
            slot="start"
            name="ion:checkmark-outline"
            aria-hidden="true"
          />
          <ion-label class="ion-text-wrap">
            {{ line.text }}
          </ion-label>
        </ion-item>
      </ion-list>
      <p
        v-if="note"
        class="card-text plan-card__note"
        data-testid="plan-note"
      >
        {{ note }}
      </p>
      <div
        v-if="action"
        class="plan-card__actions"
      >
        <ion-button
          expand="block"
          :fill="action.kind === 'upgrade' || action.kind === 'keep' ? 'solid' : 'outline'"
          :class="{ 'btn-neutral': action.kind === 'downgrade' }"
          :disabled="action.disabled"
          :aria-describedby="action.hint ? hintId : undefined"
          :data-testid="`plan-${action.kind}`"
          @click="run"
        >
          <HubIcon
            slot="start"
            :name="ICONS[action.kind]"
            aria-hidden="true"
          />
          {{ label }}
        </ion-button>
        <ion-note
          v-if="action.hint && action.disabled"
          :id="hintId"
          class="plan-card__hint"
          data-testid="plan-hint"
        >
          {{ action.hint }}
        </ion-note>
      </div>
    </ion-card-content>
  </ion-card>
</template>

<style scoped>
.plan-card {
  margin: 0;
  display: flex;
  flex-direction: column;
}
.plan-card.is-current {
  border-color: color-mix(in oklab, var(--ion-color-primary) 45%, var(--ion-border-color));
}
.plan-card__content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1 1 auto;
}
.plan-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.card-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.card-text {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.45;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.plan-card__price {
  font-family: var(--font-display, inherit);
  font-size: 1.6rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.1;
  color: var(--ion-text-color);
}
.plan-card__price small {
  font-size: 0.85rem;
  font-weight: 400;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
/* The features: Ionic's list, as compact as the mockups' checklist (no row height, no inset). */
.plan-card__features {
  margin: 0;
  padding: 0;
  background: transparent;
}
.plan-card__features ion-item {
  --background: transparent;
  --min-height: 0;
  --padding-start: 0;
  --inner-padding-end: 0;
  --padding-top: 3px;
  --padding-bottom: 3px;
  font-size: 0.9rem;
}
.plan-card__features ion-item ion-label {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.4;
  color: var(--ion-text-color);
}
.plan-card__features ion-icon {
  margin: 2px 8px 0 0;
  align-self: flex-start;
  font-size: 16px;
  color: var(--ep-success-text, var(--ion-color-success));
}
.plan-card__note {
  color: var(--ion-text-color);
}
.plan-card__actions {
  margin-top: auto;
  padding-top: 4px;
}
.plan-card__actions ion-button {
  margin: 0;
}
.plan-card__hint {
  display: block;
  margin: 6px 0 0;
  font-size: 0.82rem;
  /* Ionic's note is a faded grey (2.43:1, audit R-10): the panel's secondary text instead. */
  --color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.btn-neutral {
  --color: var(--ion-text-color);
  --border-color: var(--ion-border-color);
}
</style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
