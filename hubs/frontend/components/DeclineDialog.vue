<script setup lang="ts">
// «Decline» an invitation (README §5, U-06; mockups `launch.html`, `businesses.html`,
// `invitation.html` «reject»): a ConfirmDialog that names who invited and to what, «Cancel» first.
// Declining runs `hubs.invitation.decline` (the invitation's row goes, round 17 §2.8), says so in a
// toast, closes and tells the page (`declined`); a refusal stays in the dialog.
import { ConfirmDialog } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import type { InvitationOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';

const props = defineProps<{
  /** The invitation to decline; nothing is shown without one. */
  invitation: InvitationOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ declined: [invitation: InvitationOut] }>();

const { t } = useI18n();
const { forDialog } = useErrorText();
const decline = useCommand('hubs.invitation.decline');

const message = computed(() => {
  const invitation = props.invitation;
  if (!invitation) return '';
  return invitation.invited_by
    ? t('hubs.invitation.declineMessage', { inviter: invitation.invited_by, name: invitation.hub.name })
    : t('hubs.invitation.declineMessageNoInviter', { name: invitation.hub.name });
});

async function confirm(): Promise<void> {
  const invitation = props.invitation;
  if (!invitation) return;
  try {
    await decline.run({ id: invitation.id });
  } catch {
    return; // `decline.error` is shown in the dialog.
  }
  void toastSuccess(t('hubs.invitation.declined'));
  open.value = false;
  emit('declined', invitation);
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    testid="decline-dialog"
    tone="danger"
    confirm-icon="ion:close-outline"
    :title="$t('hubs.invitation.declineTitle')"
    :message="message"
    :confirm-label="$t('hubs.invitation.decline')"
    :pending="decline.pending.value"
    :error="forDialog(decline.error.value)"
    @confirm="confirm"
    @cancel="decline.error.value = null"
  />
</template>
