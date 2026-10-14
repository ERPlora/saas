<script setup lang="ts">
// «Cancel plan» of a row of Subscriptions (mockups `billing.html` «modal-cancel»; README §3b; UX-AUDIT-4 W-F1,
// X-08, X-31; PLAN-SAAS §3.3): a ConfirmDialog that speaks of THAT business and its own dates:
//   - it stays on its plan until the end of the period, then goes to Free without another charge;
//   - its paid modules turn off then, and nothing is deleted;
//   - what Free covers, against the people it has now (`hubs.business.get` seats: members and invitations);
//   - an unpaid invoice stays pending: cancelling does not cancel it;
//   - «Keep the plan» undoes it until then.
// Confirmed, `billing.plan.cancel` (the whole subscription, at the end of the period) and a toast that says
// until when; a refusal stays in the dialog. Web only: Subscriptions renders it in `<WebOnly>`.
import { type ConfirmConsequence, ConfirmDialog } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../../../hubs/frontend/error-text';
import type { InvoiceRowOut, PlanOut, SubscriptionRowOut } from '../../../frontend/sdk-types';
import { formatDate } from '../format';
import { formatAmount } from '../invoices';

const props = defineProps<{
  /** The row whose plan is cancelled. */
  row: SubscriptionRowOut | null;
  /** The name of each module (`apps.app.list`), by slug. */
  moduleNames: Readonly<Record<string, string>>;
  /** The Free plan (`hubs.plan.list`): what it covers. */
  freePlan: Pick<PlanOut, 'max_users' | 'max_devices'> | null;
  /** The invoice the business owes, if any. */
  unpaid: InvoiceRowOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ done: [] }>();

const { t, locale } = useI18n();
const { forDialog } = useErrorText();
const client = useLiveClient();
const cancel = useCommand('billing.plan.cancel');

/** People on the business now (members and live invitations); `null` until known. */
const people = shallowRef<number | null>(null);
let asking = 0;

watch(
  () => [open.value, props.row?.business.id] as const,
  async ([isOpen, id]) => {
    if (!isOpen || !id) return;
    cancel.error.value = null;
    people.value = null;
    const mine = ++asking;
    try {
      const business = await client.api.call('hubs.business.get', { id });
      if (mine === asking) people.value = business.seats.used;
    } catch (error) {
      console.error('billing: the people of the business could not be read for «Cancel plan»', error);
    }
  },
  { immediate: true },
);

const date = computed(() => formatDate(props.row?.next_invoice?.date ?? props.row?.ends_at ?? null, locale.value));
const plan = computed(() => props.row?.plan.name ?? '');
const name = computed(() => props.row?.business.name ?? '');

function list(names: string[]): string {
  return new Intl.ListFormat(locale.value, { style: 'long', type: 'conjunction' }).format(names);
}

const consequences = computed<ConfirmConsequence[]>(() => {
  const row = props.row;
  if (!row) return [];
  const lines: ConfirmConsequence[] = [
    {
      icon: 'ion:calendar-outline',
      text: date.value ? t('billing.cancelPlan.until', { plan: plan.value, date: date.value }) : t('billing.cancelPlan.untilNoDate', { plan: plan.value }),
    },
  ];
  const modules = row.modules.map((module) => props.moduleNames[module.slug] ?? module.slug);
  if (modules.length) {
    const values = { modules: list(modules), date: date.value };
    lines.push({
      icon: 'ion:apps-outline',
      text: date.value ? t('billing.subscriptions.cancel.modules', values, modules.length) : t('billing.subscriptions.cancel.modulesNoDate', values, modules.length),
    });
  }
  const free = props.freePlan;
  if (free && free.max_users && free.max_devices) {
    let text = t('billing.cancelPlan.limits', {
      users: t('billing.cancelPlan.users', { count: free.max_users }, free.max_users),
      devices: t('billing.cancelPlan.devices', { count: free.max_devices }, free.max_devices),
    });
    if (people.value !== null) {
      const values = { name: name.value, people: t('billing.subscriptions.cancel.people', { count: people.value }, people.value), date: date.value };
      let seats: string;
      if (people.value <= free.max_users) seats = t('billing.subscriptions.cancel.seatsFit', values);
      else seats = date.value ? t('billing.subscriptions.cancel.seatsOver', values) : t('billing.subscriptions.cancel.seatsOverNoDate', values);
      text = `${text} ${seats}`;
    }
    lines.push({ icon: 'ion:people-outline', text });
  }
  const unpaid = props.unpaid;
  if (unpaid) {
    lines.push({
      icon: 'ion:card-outline',
      text: t('billing.subscriptions.cancel.unpaid', {
        date: formatDate(unpaid.date, locale.value, 'UTC'),
        amount: formatAmount(unpaid.total_cents, unpaid.currency, locale.value),
      }),
    });
  }
  lines.push({ icon: 'ion:refresh-outline', text: t('billing.cancelPlan.undo') });
  return lines;
});

async function confirm(): Promise<void> {
  const row = props.row;
  if (!row?.business.id) return;
  try {
    const out = await cancel.run({ hub_id: row.business.id });
    const until = formatDate(out.current_period_end, locale.value);
    const values = { business: row.business.name, plan: row.plan.name, date: until };
    void toastSuccess(until ? t('billing.subscriptions.cancel.done', values) : t('billing.subscriptions.cancel.doneNoDate', values));
    open.value = false;
    emit('done');
  } catch {
    // `cancel.error`: the dialog says it.
  }
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    testid="cancel-plan"
    tone="danger"
    confirm-icon="ion:close-circle-outline"
    size="md"
    :title="$t('billing.cancelPlan.title')"
    :message="row ? $t('billing.cancelPlan.subject', { business: name, plan }) : ''"
    :consequences="consequences"
    :confirm-label="$t('billing.cancelPlan.confirm')"
    :cancel-label="$t('billing.cancelPlan.back')"
    :pending="cancel.pending.value"
    :error="forDialog(cancel.error.value)"
    @confirm="confirm"
  />
</template>
