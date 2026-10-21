<script setup lang="ts">
// The Store on the web (round 17 §2.10–§2.11; mockups `store.html`; README §3, §4 and §6.18; UX-AUDIT-4):
// the business it sells to, that business's unpaid invoice if any, and then Plans or Modules. Only the
// owner buys for a business, so the picker lists the businesses the account owns (`hubs.business.list`,
// live); `?business=` chooses the one it came from, and an unknown one falls back to the first that can buy (not
// one an unpaid invoice blocks), saying so.
//   - Plans: `hubs.plan.list`, with a monthly/annual switch and a promo code (`billing.promo.check`); the ones the
//     business is not offered yet (upgrades of a paid plan, `billing.store.catalog`'s `offered_plans`) are named in
//     one line under them (audit 2 S-03).
//   - Modules: `apps.app.list` (name, summary and icon in the person's language; asked again when the
//     language changes) joined by slug with `billing.store.catalog` (net prices, what the business has).
//   - A business Stripe does not bill yet buys in the Embedded Checkout (CheckoutModal); one that pays
//     confirms with its proration, one dialog per module (ProrationDialog), and switches its own plan's
//     billing with the total with VAT (AnnualSwitchDialog). «Downgrade to Free» cancels at the end of
//     the period (ConfirmDialog with the dates and Free's limits); «Cancel module» ends a bought module with
//     its period (ConfirmDialog with the date, BILLING-G66); «Keep» undoes a cancellation.
//   - After buying a module, «Activating… in <business>»: never on sale twice.
//   - An unpaid invoice blocks what charges for THAT business, says why and where to pay.
// Web only: StorePage renders it in `<WebOnly>`, so inside the apps nothing here loads.
import { ConfirmDialog, type ConfirmConsequence, EmptyState, InlineFeedback } from '@erplora/ui/components';
import { HubIcon, toastInfo, toastSuccess } from '@erplora/ui/shell';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonInput, IonLabel, IonSegment, IonSegmentButton, IonSkeletonText } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useLiveState } from '../../../frontend/live-state';
import { useErrorText } from '../../../hubs/frontend/error-text';
import type {
  AppSummaryOut,
  BillingInterval,
  PlanOut,
  PromoCheckOut,
  SubscriptionModuleOut,
  StoreCatalogOut,
  SubscriptionOut,
} from '../../../frontend/sdk-types';
import { formatDate } from '../format';
import {
  annualSaving,
  blockOf,
  declinedCard,
  isFree,
  moduleInterval,
  ownedBusinesses,
  saleModules,
  type SaleModule,
} from '../store';
import AnnualSwitchDialog from './AnnualSwitchDialog.vue';
import BusinessPicker from './BusinessPicker.vue';
import CheckoutModal, { type CheckoutPurchase } from './CheckoutModal.vue';
import ModuleCard from './ModuleCard.vue';
import PlanCard from './PlanCard.vue';
import ProrationDialog, { type ProrationItem } from './ProrationDialog.vue';

const props = defineProps<{
  tab: 'plans' | 'modules';
  /** `?business=`: the business the Store was opened for. */
  businessId?: string;
}>();

const emit = defineEmits<{ 'update:businessId': [id: string] }>();

const { t, locale } = useI18n();
const { forDialog } = useErrorText();
const client = useLiveClient();

// --- The business it sells to ----------------------------------------------------------------------

const list = useLive('hubs.business.list', { limit: 100 });
/** Loading, failed (the query, the stream, or nothing in time), none owned or some: «You have no business to
 *  buy for» only with a real answer (audit 2026-10-14, R-04). */
const listState = useLiveState(list, { isEmpty: (data) => ownedBusinesses(data.rows).length === 0 });
const rows = computed(() => list.data.value?.rows ?? []);
const owned = computed(() => ownedBusinesses(rows.value));
/** What the owner picked here; until then, `?business=`. */
const picked = shallowRef<string | null>(null);
const wanted = computed(() => picked.value ?? props.businessId ?? null);
/** The one asked for; else the first that can buy (not one an unpaid invoice blocks, audit 2 R-17); else the first. */
const business = computed(
  () =>
    owned.value.find((row) => row.id === wanted.value) ??
    owned.value.find((row) => !blockOf(row)) ??
    owned.value[0] ??
    null,
);
const unknownAsked = computed(
  () => !picked.value && !!props.businessId && !!list.data.value && !!business.value && business.value.id !== props.businessId,
);
const chosenId = computed({
  get: () => business.value?.id ?? '',
  set: (id: string) => {
    picked.value = id;
    emit('update:businessId', id);
  },
});
const block = computed(() => (business.value ? blockOf(business.value) : null));
/** The business whose card, the same payer's as this one, the bank declined: the checkout says so (R-21). */
const declinedFor = computed(() => (business.value ? declinedCard(rows.value, business.value) : null));

// --- What is on sale, and what the business has ------------------------------------------------------

const plans = shallowRef<PlanOut[] | null>(null);
const apps = shallowRef<AppSummaryOut[] | null>(null);
const catalog = shallowRef<StoreCatalogOut | null>(null);
const failed = shallowRef(false);
let catalogToken = 0;

async function loadOnSale(): Promise<void> {
  try {
    const [planList, appList] = await Promise.all([
      client.api.call('hubs.plan.list'),
      client.api.call('apps.app.list', { premium: true }),
    ]);
    plans.value = planList.plans;
    apps.value = appList.apps;
  } catch (error) {
    console.error('billing: the plans or the app catalog could not be loaded', error);
    failed.value = true;
  }
}

async function loadCatalog(hubId: string): Promise<void> {
  const mine = ++catalogToken;
  try {
    const answer = await client.api.call('billing.store.catalog', { hub_id: hubId });
    if (mine === catalogToken) catalog.value = answer;
  } catch (error) {
    if (mine !== catalogToken) return;
    console.error('billing: what the business has could not be loaded', error);
    failed.value = true;
  }
}

function retry(): void {
  failed.value = false;
  void loadOnSale();
  if (business.value) void loadCatalog(business.value.id);
}

// The catalog speaks the person's language: asked again when it changes.
watch(locale, () => void loadOnSale(), { immediate: true });
watch(
  () => business.value?.id,
  (id) => {
    if (id) void loadCatalog(id);
  },
  { immediate: true },
);

const subscription = computed(() => (catalog.value?.hub_id === business.value?.id ? (catalog.value?.subscription ?? null) : null));
const ready = computed(
  () => !!business.value && !!plans.value && !!apps.value && !!catalog.value && catalog.value.hub_id === business.value.id,
);
const noBusiness = computed(() => listState.view.value === 'empty');
const listFailed = listState.failed;
const modules = computed(() => saleModules(apps.value ?? [], catalog.value?.modules ?? []));
const interval = computed(() => moduleInterval(subscription.value));
const saving = computed(() => annualSaving(plans.value ?? []));
const freePlan = computed(() => plans.value?.find((plan) => isFree(plan)) ?? null);
/** What the business may move to (`billing.store.catalog`): no upgrade-only plan while Stripe does not bill it. */
const offered = computed(() => new Set(catalog.value?.offered_plans ?? []));
/** Free, the plan it has and the ones it is offered (audit 2 S-03). */
const shownPlans = computed(() =>
  (plans.value ?? []).filter((plan) => isFree(plan) || plan.slug === subscription.value?.plan || offered.value.has(plan.slug)),
);
/** The upgrades it is not offered yet, and the first plan that opens them: «Pro and Max: available after moving to
 *  Starter». */
const later = computed(() => {
  const waiting = (plans.value ?? []).filter((plan) => !shownPlans.value.includes(plan));
  const first = shownPlans.value.find((plan) => offered.value.has(plan.slug));
  if (!waiting.length || !first) return '';
  const names = new Intl.ListFormat(locale.value, { type: 'conjunction' }).format(waiting.map((plan) => plan.name));
  return t('billing.plans.later', { plans: names, plan: first.name });
});
const currentPlan = computed(() => plans.value?.find((plan) => plan.slug === subscription.value?.plan) ?? null);
const renewal = computed(() => subscription.value?.current_period_end ?? null);
/** Bought in this visit: `<business>:<module>`. */
const activating = shallowRef(new Set<string>());

// The switch starts at the billing the business pays.
const period = shallowRef<BillingInterval>('month');
watch(subscription, (now, before) => {
  if (now && now.paying && (!before || before.plan !== now.plan || before.billing_interval !== now.billing_interval)) {
    period.value = now.billing_interval;
  }
});

// --- Promo code (a plan bought on Free) -------------------------------------------------------------

const promoOpen = shallowRef(false);
const promoTyped = shallowRef('');
const promo = shallowRef<PromoCheckOut | null>(null);
const promoPending = shallowRef(false);
const promoError = shallowRef('');
const promoCode = computed(() => (promo.value?.valid ? promo.value.code : ''));
const offersPromo = computed(() => !subscription.value?.paying || subscription.value.plan === freePlan.value?.slug);

async function applyPromo(): Promise<void> {
  const code = promoTyped.value.trim();
  if (!code) return;
  promoPending.value = true;
  promoError.value = '';
  try {
    promo.value = await client.api.call('billing.promo.check', { code });
  } catch (error) {
    promo.value = null;
    promoError.value = forDialog(error as never)?.message ?? '';
  } finally {
    promoPending.value = false;
  }
}

function removePromo(): void {
  promo.value = null;
  promoTyped.value = '';
}

// --- Buying ----------------------------------------------------------------------------------------

const checkoutOpen = shallowRef(false);
const purchase = shallowRef<CheckoutPurchase | null>(null);
const prorationOpen = shallowRef(false);
const prorationItem = shallowRef<ProrationItem | null>(null);
const annualOpen = shallowRef(false);
const annualInterval = shallowRef<BillingInterval>('year');

const cents = (euros: string) => Math.round(Number(euros) * 100);

function upgrade(plan: PlanOut, chosen: BillingInterval): void {
  purchase.value = { kind: 'plan', slug: plan.slug, name: plan.name, interval: chosen };
  checkoutOpen.value = true;
}

function change(plan: PlanOut, chosen: BillingInterval): void {
  prorationItem.value = {
    kind: 'plan',
    slug: plan.slug,
    name: plan.name,
    from: currentPlan.value?.name ?? subscription.value?.plan ?? '',
    recurringCents: cents(chosen === 'year' ? plan.price_annual : plan.price_monthly),
    interval: chosen,
  };
  prorationOpen.value = true;
}

function switchBilling(chosen: BillingInterval): void {
  annualInterval.value = chosen;
  annualOpen.value = true;
}

function addModule(module: SaleModule): void {
  if (!subscription.value?.paying) {
    purchase.value = { kind: 'module', slug: module.slug, name: module.name, interval: 'month' };
    checkoutOpen.value = true;
    return;
  }
  prorationItem.value = {
    kind: 'module',
    slug: module.slug,
    name: module.name,
    recurringCents: interval.value === 'year' ? module.priceAnnualCents : module.priceMonthlyCents,
    interval: interval.value,
  };
  prorationOpen.value = true;
}

/** What a command left of the subscription, kept here until the catalog is asked again. */
function apply(out: SubscriptionOut): void {
  const now = catalog.value;
  if (!now || now.hub_id !== out.hub_id) return;
  const items = new Map<string, SubscriptionModuleOut>(out.modules.map((item) => [item.slug, item]));
  const nowTime = Date.now();
  catalog.value = {
    ...now,
    subscription: {
      plan: out.plan,
      billing_interval: out.billing_interval,
      status: out.status,
      paying: true,
      cancel_at_period_end: out.cancel_at_period_end,
      current_period_end: out.current_period_end,
      trial_plan: now.subscription?.trial_plan ?? null,
      trial_end: out.trial_end,
    },
    modules: now.modules.map((module) => {
      const item = items.get(module.slug);
      const live = !!item && (!item.valid_until || Date.parse(item.valid_until) > nowTime);
      return {
        ...module,
        owned: live,
        source: live ? (item.source as 'plan' | 'purchase') : null,
        valid_until: live ? item.valid_until : null,
      };
    }),
  };
}

function prorationDone(out: SubscriptionOut): void {
  const item = prorationItem.value;
  if (item?.kind === 'module') activating.value = new Set([...activating.value, `${out.hub_id}:${item.slug}`]);
  apply(out);
}

function stale(): void {
  void toastInfo(t('billing.checkout.stale'));
  if (business.value) void loadCatalog(business.value.id);
}

// --- Cancel and keep --------------------------------------------------------------------------------

const cancelOpen = shallowRef(false);
const cancelPlan = useCommand('billing.plan.cancel');
const keepPlan = useCommand('billing.plan.keep');
const keepModule = useCommand('billing.module.keep');
const cancelModule = useCommand('billing.module.cancel');
const { text } = useErrorText();

const cancelConsequences = computed<ConfirmConsequence[]>(() => {
  const plan = currentPlan.value?.name ?? '';
  const date = formatDate(renewal.value, locale.value);
  const lines: ConfirmConsequence[] = [
    {
      icon: 'ion:calendar-outline',
      text: date ? t('billing.cancelPlan.until', { plan, date }) : t('billing.cancelPlan.untilNoDate', { plan }),
    },
  ];
  const free = freePlan.value;
  if (free && free.max_users && free.max_devices) {
    lines.push({
      icon: 'ion:people-outline',
      text: t('billing.cancelPlan.limits', {
        users: t('billing.cancelPlan.users', { count: free.max_users }, free.max_users),
        devices: t('billing.cancelPlan.devices', { count: free.max_devices }, free.max_devices),
      }),
    });
  }
  lines.push({ icon: 'ion:refresh-outline', text: t('billing.cancelPlan.undo') });
  if (block.value) lines.push({ icon: 'ion:card-outline', text: t('billing.cancelPlan.unpaid') });
  return lines;
});

async function confirmCancel(): Promise<void> {
  const hub = business.value;
  if (!hub) return;
  try {
    const out = await cancelPlan.run({ hub_id: hub.id });
    apply(out);
    const plan = currentPlan.value?.name ?? out.plan;
    const date = formatDate(out.current_period_end, locale.value);
    void toastSuccess(date ? t('billing.cancelPlan.done', { plan, date }) : t('billing.cancelPlan.doneNoDate', { plan }));
    cancelOpen.value = false;
  } catch {
    // `cancelPlan.error`: the dialog says it.
  }
}

async function keepThePlan(): Promise<void> {
  const hub = business.value;
  if (!hub) return;
  try {
    const out = await keepPlan.run({ hub_id: hub.id });
    apply(out);
    void toastSuccess(t('billing.plans.kept', { plan: currentPlan.value?.name ?? out.plan, date: formatDate(out.current_period_end, locale.value) }));
  } catch {
    void toastInfo(text(keepPlan.error.value));
  }
}

// A bought module ends with its period (BILLING-G66): the dialog says until when and that it can be kept.
const moduleToCancel = shallowRef<SaleModule | null>(null);
const cancelModuleOpen = computed({
  get: () => moduleToCancel.value !== null,
  set: (open: boolean) => {
    if (!open) moduleToCancel.value = null;
  },
});

function askToCancel(module: SaleModule): void {
  cancelModule.error.value = null;
  moduleToCancel.value = module;
}

const cancelModuleConsequences = computed<ConfirmConsequence[]>(() => {
  const module = moduleToCancel.value?.name ?? '';
  const name = business.value?.name ?? '';
  const date = formatDate(renewal.value, locale.value);
  return [
    {
      icon: 'ion:calendar-outline',
      text: date
        ? t('billing.cancelModule.until', { module, business: name, date })
        : t('billing.cancelModule.untilNoDate', { module, business: name }),
    },
    { icon: 'ion:folder-outline', text: t('billing.cancelModule.data') },
    { icon: 'ion:refresh-outline', text: t('billing.cancelModule.undo') },
  ];
});

async function confirmCancelModule(): Promise<void> {
  const hub = business.value;
  const module = moduleToCancel.value;
  if (!hub || !module) return;
  try {
    const out = await cancelModule.run({ hub_id: hub.id, module: module.slug });
    apply(out);
    const until = out.modules.find((item) => item.slug === module.slug)?.valid_until ?? out.current_period_end;
    const date = formatDate(until, locale.value);
    void toastSuccess(
      date ? t('billing.cancelModule.done', { module: module.name, date }) : t('billing.cancelModule.doneNoDate', { module: module.name }),
    );
    moduleToCancel.value = null;
  } catch {
    // `cancelModule.error`: the dialog says it.
  }
}

async function keepTheModule(module: SaleModule): Promise<void> {
  const hub = business.value;
  if (!hub) return;
  try {
    const out = await keepModule.run({ hub_id: hub.id, module: module.slug });
    apply(out);
    const date = formatDate(out.current_period_end, locale.value);
    void toastSuccess(date ? t('billing.modules.kept', { module: module.name, date }) : t('billing.modules.keptNoDate', { module: module.name }));
  } catch {
    void toastInfo(text(keepModule.error.value));
  }
}
</script>

<template>
  <div class="store">
    <InlineFeedback
      v-if="failed || listFailed"
      tone="danger"
      :heading="listFailed ? $t('billing.store.businessesError') : $t('billing.store.loadError')"
      data-testid="store-error"
    >
      {{ $t('billing.store.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          data-testid="store-retry"
          @click="listFailed ? listState.retry() : retry()"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
            aria-hidden="true"
          />
          {{ $t('billing.store.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <EmptyState
      v-else-if="noBusiness"
      icon="storefront-outline"
      :heading="$t('billing.store.noBusiness.title')"
      :message="$t('billing.store.noBusiness.body')"
      data-testid="store-no-business"
    >
      <template #action>
        <ion-button router-link="/businesses">
          {{ $t('billing.store.noBusiness.action') }}
        </ion-button>
      </template>
    </EmptyState>

    <template v-else>
      <BusinessPicker
        v-if="business"
        v-model="chosenId"
        :businesses="owned"
      />

      <InlineFeedback
        v-if="unknownAsked && business"
        tone="neutral"
        role="status"
        data-testid="store-unknown-business"
      >
        {{ $t('billing.store.unknownBusiness', { name: business.name }) }}
      </InlineFeedback>

      <InlineFeedback
        v-if="business && block"
        tone="danger"
        icon="ion:card-outline"
        role="alert"
        :heading="$t('billing.unpaid.heading', { name: business.name })"
        data-testid="store-unpaid"
      >
        {{ $t(`billing.unpaid.${block}`) }}
        <template #actions>
          <ion-button
            v-if="business.pay_url && block !== 'card_declined'"
            size="small"
            :href="business.pay_url"
            data-testid="store-unpaid-pay"
          >
            <HubIcon
              slot="start"
              name="ion:card-outline"
              aria-hidden="true"
            />
            {{ $t('billing.unpaid.pay') }}
          </ion-button>
          <ion-button
            size="small"
            fill="outline"
            :router-link="`/billing?business=${business.id}`"
            data-testid="store-unpaid-billing"
          >
            <HubIcon
              slot="start"
              name="ion:receipt-outline"
              aria-hidden="true"
            />
            {{ $t('billing.unpaid.billing') }}
          </ion-button>
        </template>
      </InlineFeedback>

      <div
        v-if="!ready"
        class="card-grid"
        data-testid="store-loading"
        aria-busy="true"
      >
        <ion-card
          v-for="card in 2"
          :key="card"
        >
          <ion-card-content class="ion-padding">
            <ion-skeleton-text
              animated
              style="width: 30%; height: 16px"
            />
            <ion-skeleton-text
              animated
              style="width: 45%; height: 28px"
            />
            <ion-skeleton-text
              animated
              style="width: 100%; height: 110px"
            />
          </ion-card-content>
        </ion-card>
      </div>

      <section
        v-else-if="tab === 'plans'"
        class="store-section"
        data-testid="store-plans"
      >
        <div>
          <h2 class="section-title">
            {{ $t('billing.plans.heading') }}
          </h2>
          <p class="section-intro">
            {{ $t('billing.plans.intro') }}
          </p>
        </div>
        <ion-segment
          class="store-period"
          :value="period"
          :aria-label="$t('billing.plans.period')"
          data-testid="store-period"
          @ion-change="period = $event.detail.value === 'year' ? 'year' : 'month'"
        >
          <ion-segment-button
            value="month"
            data-testid="store-period-month"
          >
            <ion-label>{{ $t('billing.plans.monthly') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button
            value="year"
            data-testid="store-period-year"
          >
            <ion-label>{{ saving ? $t('billing.plans.annualSaving', { percent: saving }) : $t('billing.plans.annual') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
        <div class="card-grid">
          <PlanCard
            v-for="plan in shownPlans"
            :key="plan.slug"
            :plan="plan"
            :period="period"
            :subscription="subscription"
            :block="block"
            @upgrade="upgrade(plan, $event)"
            @change="change(plan, $event)"
            @switch="switchBilling($event)"
            @downgrade="cancelOpen = true"
            @keep="keepThePlan"
          />
        </div>
        <p
          v-if="later"
          class="section-intro"
          data-testid="store-plans-later"
        >
          {{ later }}
        </p>
        <div
          v-if="offersPromo"
          class="store-promo"
        >
          <ion-button
            v-if="!promoOpen"
            fill="clear"
            class="link-button"
            data-testid="store-promo-toggle"
            @click="promoOpen = true"
          >
            <HubIcon
              slot="start"
              name="ion:ticket-outline"
              aria-hidden="true"
            />
            {{ $t('billing.promo.ask') }}
          </ion-button>
          <form
            v-else
            class="store-promo__form"
            novalidate
            @submit.prevent="applyPromo"
          >
            <ion-input
              mode="md"
              fill="outline"
              label-placement="floating"
              autocapitalize="characters"
              :label="$t('billing.promo.label')"
              :value="promoTyped"
              data-testid="store-promo-code"
              @ion-input="promoTyped = String($event.detail.value ?? '')"
            />
            <ion-button
              fill="outline"
              :disabled="promoPending || !promoTyped.trim()"
              data-testid="store-promo-apply"
              @click="applyPromo"
            >
              <HubIcon
                slot="start"
                name="ion:checkmark-outline"
                aria-hidden="true"
              />
              {{ $t('billing.promo.apply') }}
            </ion-button>
            <ion-button
              v-if="promo"
              fill="clear"
              class="btn-neutral"
              data-testid="store-promo-remove"
              @click="removePromo"
            >
              <HubIcon
                slot="start"
                name="ion:close-outline"
                aria-hidden="true"
              />
              {{ $t('billing.promo.remove') }}
            </ion-button>
          </form>
          <p
            v-if="promo || promoError"
            class="store-promo__result"
            :class="{ 'is-invalid': !promo?.valid }"
            role="status"
            data-testid="store-promo-result"
          >
            {{ promoError || (promo?.valid ? $t('billing.promo.valid', { code: promo.code, days: promo.trial_days }) : $t('billing.promo.invalid')) }}
          </p>
        </div>
      </section>

      <section
        v-else
        class="store-section"
        data-testid="store-modules"
      >
        <div>
          <h2 class="section-title">
            {{ $t('billing.modules.heading') }}
          </h2>
          <p class="section-intro">
            {{ $t('billing.modules.intro') }}
          </p>
        </div>
        <div
          v-if="modules.length"
          class="card-grid cols-3"
        >
          <ModuleCard
            v-for="module in modules"
            :key="module.slug"
            :module="module"
            :interval="interval"
            :block="block"
            :activating="activating.has(`${business?.id}:${module.slug}`)"
            :business-name="business?.name ?? ''"
            :renewal="renewal"
            @add="addModule(module)"
            @keep="keepTheModule(module)"
            @cancel="askToCancel(module)"
          />
        </div>
        <EmptyState
          v-else
          icon="apps-outline"
          :heading="$t('billing.modules.empty')"
          data-testid="store-no-modules"
        />
      </section>
    </template>

    <CheckoutModal
      v-if="business"
      v-model:open="checkoutOpen"
      :business="{ id: business.id, name: business.name }"
      :purchase="purchase"
      :promo-code="purchase?.kind === 'plan' ? promoCode : ''"
      :declined-for="declinedFor"
      @stale="stale"
    />
    <ProrationDialog
      v-if="business"
      v-model:open="prorationOpen"
      :business="{ id: business.id, name: business.name }"
      :item="prorationItem"
      :renewal="renewal"
      :promo-code="promoCode"
      @done="prorationDone"
      @checkout="stale"
    />
    <AnnualSwitchDialog
      v-if="business"
      v-model:open="annualOpen"
      :business="{ id: business.id, name: business.name }"
      :plan="currentPlan"
      :interval="annualInterval"
      @done="apply"
    />
    <ConfirmDialog
      v-if="business"
      v-model:open="cancelOpen"
      testid="store-cancel"
      :title="$t('billing.cancelPlan.title')"
      :message="$t('billing.cancelPlan.subject', { business: business.name, plan: currentPlan?.name ?? '' })"
      :consequences="cancelConsequences"
      :confirm-label="$t('billing.cancelPlan.confirm')"
      :cancel-label="$t('billing.cancelPlan.back')"
      confirm-icon="ion:close-circle-outline"
      :pending="cancelPlan.pending.value"
      :error="forDialog(cancelPlan.error.value)"
      @confirm="confirmCancel"
    />
    <ConfirmDialog
      v-if="business"
      v-model:open="cancelModuleOpen"
      testid="store-cancel-module"
      :title="$t('billing.cancelModule.title')"
      :message="$t('billing.cancelModule.subject', { business: business.name, module: moduleToCancel?.name ?? '' })"
      :consequences="cancelModuleConsequences"
      :confirm-label="$t('billing.cancelModule.confirm')"
      :cancel-label="$t('billing.cancelModule.back')"
      confirm-icon="ion:close-circle-outline"
      :pending="cancelModule.pending.value"
      :error="forDialog(cancelModule.error.value)"
      @confirm="confirmCancelModule"
    />
  </div>
</template>

<style scoped>
.store {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.store-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
/* The mockup's `.section-title`: a small monospaced eyebrow. */
.section-title {
  margin: 0;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 10.5px;
  font-weight: 400;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: color-mix(in oklch, var(--ion-text-color) 60%, transparent);
}
.section-intro {
  margin: 4px 0 0;
  font-size: 0.88rem;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
/* The billing switch is Ionic's segment as iOS paints a filter (the mockup's «Mensual | Anual»): a tinted
   track with a raised indicator, 28px buttons. The shell's polish.css restyles every segment as its
   footer tabbar (transparent, 46px tabs, the primary colour): here Ionic's own look is put back. */
.store-period {
  --background: rgba(var(--ion-text-color-rgb, 0, 0, 0), 0.065);
  width: 100%;
  max-width: 360px;
  padding: 2px;
  gap: 0;
  border-radius: 9px;
}
.store-period ion-segment-button {
  --indicator-color: var(--ion-card-background, var(--ion-background-color, #fff));
  --indicator-box-shadow: 0 0 5px rgba(0, 0, 0, 0.16);
  --color: var(--ion-text-color);
  --color-checked: var(--ion-text-color);
  --border-radius: 7px;
  min-height: 28px;
  font-size: 13px;
  font-weight: 500;
}
.store-period ion-segment-button::part(indicator-background) {
  border-radius: 7px;
}
/* A phone or a touch screen: 44 px to tap (audit 2026-10-14, R-13; `frontend/panel-chrome.css`). */
@media (max-width: 640px), (pointer: coarse) {
  .store-period ion-segment-button {
    min-height: 44px;
  }
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
.card-grid.cols-3 {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}
.card-grid > ion-card {
  margin: 0;
}
.store-promo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.store-promo__form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  width: 100%;
  max-width: 480px;
}
.store-promo__form ion-input {
  flex: 1 1 200px;
}
.store-promo__result {
  margin: 0;
  font-size: 0.88rem;
  color: var(--ep-success-text, var(--ion-color-success));
}
.store-promo__result.is-invalid {
  color: var(--ep-danger-text, var(--ion-color-danger));
}
.link-button {
  margin: 0;
}
.btn-neutral {
  --color: var(--ion-text-color);
}
</style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
