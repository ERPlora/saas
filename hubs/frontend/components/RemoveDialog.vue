<script setup lang="ts">
// «Remove» a member or «Cancel invitation» (mockups `business.html` «members-remove»,
// «members-cancel-invite»; README §3b: confirm whatever leaves somebody out). An answered member is
// removed from this business only (`hubs.member.remove`: their account and other businesses stay, the
// Hub ends their sessions); an invitation is withdrawn (`hubs.member.cancel`: its link stops working),
// with «Back» as the way out so two «Cancel» never sit together.
import { ConfirmDialog } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { MemberRowOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';

const props = defineProps<{
  member: MemberRowOut | null;
  businessName: string;
}>();

const open = defineModel<boolean>('open', { default: false });

const { t } = useI18n();
const { forDialog } = useErrorText();
const remove = useCommand('hubs.member.remove');
const cancel = useCommand('hubs.member.cancel');

const invitation = computed(() => !!props.member && props.member.status !== 'active');
const command = computed(() => (invitation.value ? cancel : remove));

async function confirm(): Promise<void> {
  const member = props.member;
  if (!member) return;
  try {
    await command.value.run({ id: member.id });
  } catch {
    return; // The dialog shows the error.
  }
  void toastSuccess(invitation.value ? t('hubs.members.cancelInvite.done') : t('hubs.members.remove.done', { name: member.name }));
  open.value = false;
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    testid="remove-dialog"
    tone="danger"
    :confirm-icon="invitation ? 'ion:close-outline' : 'ion:trash-outline'"
    :title="invitation ? $t('hubs.members.cancelInvite.title') : $t('hubs.members.remove.title', { name: member?.name ?? '' })"
    :message="
      invitation
        ? $t('hubs.members.cancelInvite.message', { email: member?.email ?? '' })
        : $t('hubs.members.remove.message', { name: member?.name ?? '', business: businessName })
    "
    :confirm-label="invitation ? $t('hubs.members.cancelInvite.confirm') : $t('hubs.members.remove.confirm')"
    :cancel-label="invitation ? $t('hubs.members.cancelInvite.back') : undefined"
    :pending="command.pending.value"
    :error="forDialog(command.error.value)"
    @confirm="confirm"
    @cancel="command.error.value = null"
  />
</template>
