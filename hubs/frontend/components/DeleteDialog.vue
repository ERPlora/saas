<script setup lang="ts">
// «Delete business» (PLAN-SAAS §3.4, round 17 §2.11; mockups `business.html` «settings-delete»): a
// ConfirmDialog that asks to type the business's name (the server checks it too: `confirm_name`) and
// says what follows. Deleting runs `hubs.business.delete`, says until when the business can be
// recovered, closes and hands the deleted business to the page (`deleted`). Used by Businesses (row
// action) and by the Danger zone of the business's Settings; only the owner gets to open it.
import { ConfirmDialog, formatDateTime } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessDetailOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';

const props = defineProps<{
  /** The business to delete; nothing is shown without one. */
  business: { id: string; name: string } | null;
}>();

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ deleted: [business: BusinessDetailOut] }>();

const { t, locale } = useI18n();
const { forDialog } = useErrorText();
const remove = useCommand('hubs.business.delete');

const consequences = computed(() => [
  { text: t('hubs.danger.consequencePlan'), icon: 'ion:receipt-outline' },
  { text: t('hubs.danger.consequenceEmail'), icon: 'ion:mail-outline' },
]);

async function confirm(): Promise<void> {
  const business = props.business;
  if (!business) return;
  let deleted: BusinessDetailOut;
  try {
    deleted = await remove.run({ id: business.id, confirm_name: business.name });
  } catch {
    return; // `remove.error` is shown in the dialog.
  }
  void toastSuccess(t('hubs.list.deleted', { name: deleted.name, date: formatDateTime(deleted.purge_after, locale.value) }));
  open.value = false;
  emit('deleted', deleted);
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    testid="delete-dialog"
    tone="danger"
    size="md"
    confirm-icon="ion:trash-outline"
    :title="$t('hubs.danger.confirmTitle', { name: business?.name ?? '' })"
    :message="$t('hubs.danger.confirmMessage')"
    :consequences="consequences"
    :require-text="business?.name"
    :require-text-label="$t('hubs.danger.confirmLabel')"
    :confirm-label="$t('hubs.danger.deleteAction')"
    :pending="remove.pending.value"
    :error="forDialog(remove.error.value)"
    @confirm="confirm"
    @cancel="remove.error.value = null"
  />
</template>
