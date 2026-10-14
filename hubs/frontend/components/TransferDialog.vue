<script setup lang="ts">
// «Transfer ownership» (mockups `business.html` «members-transfer», round 17 §2.7; README §3b: always
// behind a confirmation): the business is offered to a member, who has 7 days to accept it; until then
// nothing changes and the invoices keep their payer. The business's name is typed to confirm.
// `hubs.ownership.transfer`, and a toast naming to whom.
import { ConfirmDialog } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { MemberRowOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';

const props = defineProps<{
  member: MemberRowOut | null;
  business: { id: string; name: string };
}>();

const open = defineModel<boolean>('open', { default: false });

const { t } = useI18n();
const { forDialog } = useErrorText();
const transfer = useCommand('hubs.ownership.transfer');

const consequences = computed(() => [
  { text: t('hubs.members.transfer.consequenceWindow'), icon: 'ion:time-outline' },
  { text: t('hubs.members.transfer.consequenceBilling'), icon: 'ion:receipt-outline' },
]);

async function confirm(): Promise<void> {
  const member = props.member;
  if (!member) return;
  try {
    const offer = await transfer.run({ hub_id: props.business.id, member_id: member.id });
    void toastSuccess(t('hubs.members.transfer.done', { email: offer.to_email }));
    open.value = false;
  } catch {
    // The dialog shows the error.
  }
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    testid="transfer-dialog"
    tone="warning"
    size="md"
    confirm-icon="ion:swap-vertical-outline"
    :title="$t('hubs.members.transfer.title', { business: business.name })"
    :message="$t('hubs.members.transfer.message', { name: member?.name ?? '' })"
    :consequences="consequences"
    :require-text="business.name"
    :require-text-label="$t('hubs.members.transfer.confirmLabel')"
    :confirm-label="$t('hubs.members.transfer.confirm')"
    :pending="transfer.pending.value"
    :error="forDialog(transfer.error.value)"
    @confirm="confirm"
    @cancel="transfer.error.value = null"
  />
</template>
