<script setup lang="ts">
// «Change role» (mockups `business.html` «members-role»): the roles the account may give this member
// (the server's `assignable_roles`; never the owner's, which only moves by a transfer),
// `hubs.member.change_role`, and a toast with the new role. A refusal stays in the dialog.
import { FormModal } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { InvitableRole, MemberRowOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';

const props = defineProps<{
  member: MemberRowOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const { t } = useI18n();
const { forDialog } = useErrorText();
const change = useCommand('hubs.member.change_role');
const role = shallowRef<InvitableRole>('hub_employee');

watch(
  [open, () => props.member],
  ([isOpen, member]) => {
    if (!isOpen || !member) return;
    const current = member.role as InvitableRole;
    role.value = member.assignable_roles.includes(current) ? current : (member.assignable_roles[0] ?? current);
    change.error.value = null;
  },
  { immediate: true },
);

async function save(): Promise<void> {
  const member = props.member;
  if (!member) return;
  try {
    const changed = await change.run({ id: member.id, role: role.value });
    void toastSuccess(t('hubs.members.roleModal.changed', { name: changed.name, role: t(`hubs.roles.${changed.role}`) }));
    open.value = false;
  } catch {
    // `change.error`: the dialog shows it.
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="role-modal"
    size="sm"
    :title="$t('hubs.members.roleModal.title', { name: member?.name ?? '' })"
    :submit-label="$t('hubs.members.roleModal.submit')"
    submit-icon="ion:create-outline"
    :pending="change.pending.value"
    :error="forDialog(change.error.value)"
    @submit="save"
  >
    <ion-select
      data-testid="role-select"
      mode="md"
      fill="outline"
      label-placement="floating"
      interface="popover"
      :label="$t('hubs.members.roleModal.role')"
      :value="role"
      @ion-change="role = String($event.detail.value) as InvitableRole"
    >
      <ion-select-option
        v-for="option in member?.assignable_roles ?? []"
        :key="option"
        :value="option"
      >
        {{ $t(`hubs.roles.${option}`) }}
      </ion-select-option>
    </ion-select>
  </FormModal>
</template>
