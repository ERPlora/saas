<script setup lang="ts">
// «Invite» (mockups `business.html` «members-invite», round 17 §2.8): the email, the role (only those
// the account may hand out: the server's `invitable_roles`, employee by default) and an optional
// message. `hubs.member.invite` creates the invitation (and the account if needed) and mails it; the
// toast names who was invited. With every place of the plan taken (the list's `seats`, or the server's
// 409 `hubs.seat_limit` when somebody took the last one meanwhile) it says so and sends nothing more; it waits
// for an email that looks like one (audit 2 R-28); a
// 422 puts its message on its field; anything else stays in the dialog, said in the person's language.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { looksLikeEmail } from '../../../frontend/email';
import type { InvitableRole, SeatsOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';

const props = defineProps<{
  business: { id: string; name: string };
  /** The roles the account may invite with (`hubs.member.list`'s `invitable_roles`). */
  invitableRoles: InvitableRole[];
  seats: SeatsOut;
}>();

const open = defineModel<boolean>('open', { default: false });

const { t } = useI18n();
const { forDialog } = useErrorText();
const invite = useCommand('hubs.member.invite');

const email = shallowRef('');
const role = shallowRef<InvitableRole>('hub_employee');
const message = shallowRef('');

const full = computed(
  () => (props.seats.limit !== null && props.seats.used >= props.seats.limit) || invite.error.value?.code === 'hubs.seat_limit',
);
/** «Send invitation» waits for an address (audit 2 R-28): the server still checks it. */
const sendable = computed(() => looksLikeEmail(email.value));

watch(open, (isOpen) => {
  if (!isOpen) return;
  email.value = '';
  message.value = '';
  role.value = props.invitableRoles.includes('hub_employee') ? 'hub_employee' : (props.invitableRoles.at(-1) ?? 'hub_employee');
  invite.error.value = null;
});

async function send(): Promise<void> {
  try {
    const invited = await invite.run({ hub_id: props.business.id, email: email.value.trim(), role: role.value, message: message.value.trim() });
    void toastSuccess(t('hubs.members.inviteModal.sent', { email: invited.email }));
    open.value = false;
  } catch {
    // `invite.error`: the dialog shows it.
  }
}

const value = (event: CustomEvent<{ value?: unknown }>) => String(event.detail.value ?? '');
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="invite-modal"
    :title="$t('hubs.members.inviteModal.title', { name: business.name })"
    :submit-label="$t('hubs.members.inviteModal.submit')"
    submit-icon="ion:mail-outline"
    :pending="invite.pending.value"
    :error="forDialog(invite.error.value)"
    :submit-disabled="full || !sendable"
    @submit="send"
  >
    <template #default="{ fieldErrors }">
      <div class="invite-fields">
        <InlineFeedback
          v-if="full"
          tone="warning"
          data-testid="invite-full"
        >
          {{ $t('hubs.members.seatsFull') }}
        </InlineFeedback>
        <ion-input
          data-testid="invite-email"
          data-autofocus
          type="email"
          mode="md"
          fill="outline"
          label-placement="floating"
          autocomplete="email"
          required
          :label="$t('hubs.members.inviteModal.email')"
          :value="email"
          :error-text="fieldErrors.email"
          :class="{ 'ion-invalid': !!fieldErrors.email, 'ion-touched': !!fieldErrors.email }"
          @ion-input="email = value($event)"
        />
        <ion-select
          data-testid="invite-role"
          mode="md"
          fill="outline"
          label-placement="floating"
          interface="popover"
          :label="$t('hubs.members.inviteModal.role')"
          :value="role"
          :error-text="fieldErrors.role"
          :class="{ 'ion-invalid': !!fieldErrors.role, 'ion-touched': !!fieldErrors.role }"
          @ion-change="role = value($event) as InvitableRole"
        >
          <ion-select-option
            v-for="option in invitableRoles"
            :key="option"
            :value="option"
          >
            {{ $t(`hubs.roles.${option}`) }}
          </ion-select-option>
        </ion-select>
        <ion-textarea
          data-testid="invite-message"
          mode="md"
          fill="outline"
          label-placement="floating"
          :auto-grow="true"
          :maxlength="500"
          :label="$t('hubs.members.inviteModal.message')"
          :value="message"
          :error-text="fieldErrors.message"
          @ion-input="message = value($event)"
        />
        <p class="invite-hint">
          {{ $t('hubs.members.inviteModal.hint') }}
          <span
            v-if="seats.limit !== null"
            data-testid="invite-seats"
          >{{ $t('hubs.members.seats', { used: seats.used, limit: seats.limit }) }}</span>
        </p>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.invite-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.invite-hint {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 12px;
  font-size: 0.8rem;
  color: color-mix(in oklab, var(--ion-text-color) 68%, transparent);
}
</style>
