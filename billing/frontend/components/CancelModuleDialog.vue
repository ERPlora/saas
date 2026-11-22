<script setup lang="ts">
// The Store's «Cancel module» of a module the business bought: it ends with its period, and the dialog says until
// when and that it can be kept. Confirmed, `billing.module.cancel`; what it left of the subscription goes to the
// Store (`done`). Open while `module` is set; closing it clears it.
import { type ConfirmConsequence, ConfirmDialog } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { SubscriptionOut } from '../../../frontend/sdk-types/store';
import { useErrorText } from '../../../hubs/frontend/error-text';
import { formatDate } from '../format';
import type { SaleModule } from '../store';

const props = defineProps<{
  business: { id: string; name: string };
  /** When the period ends: what the module works until. */
  renewal: string | null;
}>();

const moduleToCancel = defineModel<SaleModule | null>('module', { default: null });
const emit = defineEmits<{ done: [out: SubscriptionOut] }>();

const { t, locale } = useI18n();
const { forDialog } = useErrorText();
const cancelModule = useCommand('billing.module.cancel');

const cancelModuleOpen = computed({
  get: () => moduleToCancel.value !== null,
  set: (open: boolean) => {
    if (!open) moduleToCancel.value = null;
  },
});

// Asked again, the dialog does not keep the refusal of the time before.
watch(moduleToCancel, (module) => {
  if (module) cancelModule.error.value = null;
});

const cancelModuleConsequences = computed<ConfirmConsequence[]>(() => {
  const module = moduleToCancel.value?.name ?? '';
  const name = props.business.name;
  const date = formatDate(props.renewal, locale.value);
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
  const hub = props.business;
  const module = moduleToCancel.value;
  if (!module) return;
  try {
    const out = await cancelModule.run({ hub_id: hub.id, module: module.slug });
    emit('done', out);
    const until = out.modules.find((item) => item.slug === module.slug)?.valid_until ?? out.current_period_end;
    const date = formatDate(until, locale.value);
    toastSuccess(
      date ? t('billing.cancelModule.done', { module: module.name, date }) : t('billing.cancelModule.doneNoDate', { module: module.name }),
    );
    moduleToCancel.value = null;
  } catch {
    // `cancelModule.error`: the dialog says it.
  }
}
</script>

<template>
  <ConfirmDialog
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
</template>
