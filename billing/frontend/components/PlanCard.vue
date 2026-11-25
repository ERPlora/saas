<script setup lang="ts">
// A plan of the Store: its name, description, net price, features, the apps it turns on at once (`max_apps`, the
// cap the Hub applies; 0 = all), the messages a month it includes (assistant and WhatsApp; 0 = none, no line), the
// custom domain of the business's website when the plan includes one, and its trial, in the order of /pricing/'s
// cards (public/pricing.py `plan_card`). Then the ONE thing the chosen business can do with it now: the card says
// which one applies and emits it.
//   - A downgrade that waits for the end of the period: its plan says to what and when, with «Keep the plan» (it
//     charges nothing, so an unpaid invoice does not stop it).
//   - An unpaid invoice disables what charges, with the reason under the button. Cancelling is never blocked: it
//     only stops the next charges.
import { CollapsibleChecklist, StatusPill } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonNote } from '@ionic/vue';
import { computed, useId } from 'vue';
import { useI18n } from 'vue-i18n';

import type { PlanOut } from '../../../frontend/sdk-types/hubs-catalog';
import type { BillingInterval, StoreSubscriptionOut } from '../../../frontend/sdk-types/store';
import { formatDate, formatEuros } from '../format';
import { type Block, isFree } from '../store';

const props = defineProps<{
  plan: PlanOut;
  /** The billing the switch above shows. */
  period: BillingInterval;
  /** The billings Stripe sells the plan with: the ones its Stripe price is pasted for (`sold_intervals`). */
  sold: BillingInterval[];
  /** The chosen business's plan (`billing.store.catalog`); none = Free. */
  subscription: StoreSubscriptionOut | null;
  /** An unpaid invoice of the business: nothing that charges. */
  block: Block | null;
  /** The name of the plan a downgrade that waits moves the business to (`subscription.scheduled_change`). */
  scheduledPlanName?: string;
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
  /** Undo the cancellation, or the downgrade that waits. */
  keep: [];
}>();

const expanded = defineModel<boolean>('expanded', { default: false });

type Action = 'upgrade' | 'change' | 'switch' | 'downgrade' | 'keep';

const { t, locale } = useI18n();
const hintId = `plan-hint-${useId()}`;

const free = computed(() => isFree(props.plan));
const paying = computed(() => !!props.subscription?.paying);
const current = computed(() => (props.subscription ? props.subscription.plan === props.plan.slug : free.value));
const cancelling = computed(() => paying.value && !!props.subscription?.cancel_at_period_end);
const periodEnd = computed(() => formatDate(props.subscription?.current_period_end, locale.value));
/** The downgrade that waits for the end of the period (a cancellation wins over it). */
const scheduled = computed(() => (paying.value && !cancelling.value ? (props.subscription?.scheduled_change ?? null) : null));
const scheduledFrom = computed(() => formatDate(scheduled.value?.starts_at, locale.value));
const trying = computed(() => {
  const subscription = props.subscription;
  if (!subscription || paying.value || subscription.trial_plan !== props.plan.slug || !subscription.trial_end) return false;
  return Date.parse(subscription.trial_end) > Date.now();
});

/** A paid plan without an annual price (the internal one) shows its monthly price under «Annual». */
const monthlyOnly = computed(() => !free.value && Number(props.plan.price_annual) === 0);

type PlanAction = { kind: Action; disabled: boolean; hint: string };

const unpaid = computed(() => (props.block ? t('billing.plans.payFirst') : ''));
/** Why the plan is not bought with the billing the switch says: Stripe has no price for it (checkout would refuse it). */
const notSold = computed(() => {
  if (props.sold.includes(props.period)) return '';
  if (props.sold.includes('month')) return t('billing.modules.monthlyOnly');
  if (props.sold.includes('year')) return t('billing.plans.annualOnly');
  return t('billing.plans.notOnSale');
});
/** Why nothing that charges works now: an unpaid invoice, or a billing the plan is not sold with. */
const payFirst = computed(() => unpaid.value || notSold.value);

function charging(kind: Action): PlanAction {
  return { kind, disabled: !!payFirst.value, hint: payFirst.value };
}

/** Free's card cancels the paid plan, which charges nothing. */
function freeAction(): PlanAction | null {
  if (current.value || !paying.value || cancelling.value) return null;
  return { kind: 'downgrade', disabled: false, hint: '' };
}

/** The card of the plan the business pays keeps a cancellation or a downgrade that waits, or switches its billing. */
function ownPlanAction(): PlanAction | null {
  if (cancelling.value) return { kind: 'keep', disabled: !!props.block, hint: unpaid.value };
  if (scheduled.value) return { kind: 'keep', disabled: false, hint: '' };
  if (props.period !== props.subscription?.billing_interval) return charging('switch');
  return null;
}

/** Another paid plan of a business that pays is a change, unless it is the downgrade already waiting. */
function otherPlanAction(): PlanAction | null {
  if (cancelling.value) return { kind: 'change', disabled: true, hint: t('billing.plans.keepFirst') };
  const waiting = scheduled.value;
  if (waiting && waiting.plan === props.plan.slug && waiting.interval === props.period) return null;
  return charging('change');
}

/** The one button of the card, whether it works now, and why not. */
const action = computed<PlanAction | null>(() => {
  if (free.value) return freeAction();
  if (current.value && paying.value) return ownPlanAction();
  if (paying.value) return otherPlanAction();
  return charging('upgrade');
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
  if (props.period === 'year' && !monthlyOnly.value) {
    return {
      amount: formatEuros(props.plan.price_annual, locale.value),
      suffix: t('billing.plans.perYear', { monthly: formatEuros(Number(props.plan.price_annual) / 12, locale.value) }),
    };
  }
  return { amount: formatEuros(props.plan.price_monthly, locale.value), suffix: t('billing.plans.perMonth') };
});

type Line = { kind: 'feature' | 'apps' | 'quota' | 'domain'; text: string };

/** The features that say what a plan includes, in the languages its rows are written in (as /pricing/'s
 * `INCLUDES_LINES` and `INCLUDES_PREFIXES`): the apps it turns on at once go right after the first of them. */
const INCLUDES_LINES = new Set(['All apps included', 'Todas las apps incluidas']);
const INCLUDES_PREFIXES = ['Everything in ', 'Todo lo del plan '];
const saysWhatItIncludes = (feature: string) => INCLUDES_LINES.has(feature) || INCLUDES_PREFIXES.some((prefix) => feature.startsWith(prefix));

/** The lines of the card, as /pricing/ paints them: the plan's own features with the apps it turns on at once
 * right after what it includes (else at their end), the messages a month (a quota of 0 is none: no line), the custom
 * domain if the plan includes one and, last, its trial, the line `hubs.plan.list` ends a signable plan's features with. */
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
  if (plan.includes_custom_domain) result.push({ kind: 'domain', text: t('billing.plans.customDomain') });
  return [...result, ...trial.map(feature)];
});
const checklistItems = computed(() => lines.value.map((line) => ({ text: line.text, testid: `plan-${line.kind}` })));

/** The card of the paid plan the business is on tells its cancellation or the downgrade that waits; null if neither. */
function ownPlanNote(): string | null {
  if (cancelling.value) return t('billing.plans.cancelled', { plan: props.plan.name, date: periodEnd.value });
  const waiting = scheduled.value;
  if (!waiting) return null;
  if (waiting.plan === props.plan.slug) {
    return t('billing.plans.scheduledBilling', {
      plan: props.plan.name,
      from: t(`billing.plans.periodName.${props.subscription?.billing_interval ?? 'year'}`),
      date: scheduledFrom.value,
      to: t(`billing.plans.periodName.${waiting.interval}`),
    });
  }
  return t('billing.plans.scheduled', { plan: props.plan.name, date: scheduledFrom.value, next: props.scheduledPlanName || waiting.plan });
}

/** The card of a plan the business moves or may move to: the downgrade's date, Free's date, a trial's days. */
function destinationNote(): string {
  const waiting = scheduled.value;
  if (waiting && waiting.plan === props.plan.slug) return t('billing.plans.scheduledFrom', { plan: props.plan.name, date: scheduledFrom.value });
  if (free.value && cancelling.value) return t('billing.plans.freeFrom', { date: periodEnd.value });
  if (trying.value) return t('billing.plans.trialKeeps');
  return '';
}

/** What the card says under the features: a cancellation or a downgrade that waits, Free's date, a trial's days. */
const note = computed(() => (current.value && !free.value ? ownPlanNote() : null) ?? destinationNote());

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
    :class="{ 'is-current': current, 'is-featured': !!plan.featured_label }"
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
        class="card-text plan-card__description"
      >
        {{ plan.description }}
      </p>
      <div
        class="plan-card__price"
        data-testid="plan-price"
      >
        {{ price.amount }} <small>{{ price.suffix }}</small>
      </div>
      <div class="plan-card__actions">
        <p
          v-if="note"
          class="card-text plan-card__note"
          data-testid="plan-note"
        >
          {{ note }}
        </p>
        <template v-if="action">
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
        </template>
      </div>
      <CollapsibleChecklist
        v-model:expanded="expanded"
        class="plan-card__features"
        :items="checklistItems"
        :show-all-label="$t('billing.plans.showAll')"
        :show-fewer-label="$t('billing.plans.showFewer')"
        toggle-testid="plan-features-toggle"
      />
    </ion-card-content>
  </ion-card>
</template>

<style scoped>
.plan-card {
  grid-row: span 7;
  display: grid;
  grid-template-rows: repeat(7, auto);
  grid-template-rows: subgrid;
  /* Ionic's card containment disables subgrid on the host. */
  contain: none;
  min-inline-size: 0;
  margin: 0;
  border: 1px solid var(--ep-border, var(--ion-border-color));
  border-radius: 18px;
  overflow: hidden;
  overflow: clip;
}
.plan-card.is-current {
  border-color: color-mix(in oklab, var(--ion-color-primary) 55%, var(--ion-border-color));
}
.plan-card.is-featured {
  border-color: color-mix(in oklab, var(--ion-color-primary) 70%, transparent);
  background: linear-gradient(
    180deg,
    color-mix(in oklab, var(--ion-color-primary) 6%, var(--ion-card-background)),
    var(--ion-card-background)
  );
  box-shadow: 0 24px 60px -30px color-mix(in oklab, var(--ion-color-primary) 65%, transparent);
}
.plan-card__content {
  grid-row: 1 / -1;
  display: grid;
  grid-template-rows: repeat(7, auto);
  grid-template-rows: subgrid;
  min-inline-size: 0;
}
@supports not (grid-template-rows: subgrid) {
  .plan-card,
  .plan-card__content {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
}
.plan-card__head {
  grid-row: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.card-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  text-wrap: balance;
  color: var(--ion-text-color);
}
.card-text {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.45;
  text-wrap: pretty;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.plan-card__description {
  grid-row: 2;
}
.plan-card__price {
  grid-row: 3;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 6px;
  font-family: var(--font-display, inherit);
  font-size: 2.25rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1;
  color: var(--ion-text-color);
}
.plan-card__price small {
  font-size: 0.82rem;
  font-weight: 400;
  line-height: 1.4;
  letter-spacing: normal;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.plan-card__actions {
  grid-row: 4;
}
.plan-card__actions ion-button {
  min-block-size: 44px;
  margin: 0;
}
.plan-card__features {
  grid-row: 5 / span 2;
  display: grid;
  grid-template-rows: repeat(2, auto);
  grid-template-rows: subgrid;
}
@media (max-width: 639px) {
  .plan-card {
    display: block;
  }
  .plan-card__content {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .plan-card__actions:empty {
    display: none;
  }
  .plan-card__features {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
}
.plan-card__hint {
  display: block;
  margin: 6px 0 0;
  font-size: 0.82rem;
  line-height: 1.35;
  --color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.plan-card__note {
  margin-block-end: 6px;
  color: var(--ion-text-color);
}
.btn-neutral {
  --color: var(--ion-text-color);
  --border-color: var(--ion-border-color);
}
</style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
