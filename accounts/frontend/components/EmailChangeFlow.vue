<script setup lang="ts">
// The change of the sign-in email (accounts/README.md, «Correo por código propio»; mockups `account.html`, «Cambiar»
// next to the email), two steps in one dialog:
//   1. the new address → `accounts.email.change` mails it a 6-digit code (another address asks for a recent
//      sign-in first: `ReauthModal`, then it is sent again);
//   2. the code, typed in this same session → `accounts.email.verify`. The account keeps its address until then.
// A wrong code is no error of the request: the dialog says the tries left; with none left the code is gone and
// the dialog goes back to the address, which a new code needs. «Send a new code» sends it again.
// `mode`: `change` starts at the address; `verify` proves the account's own address (the code goes there at once);
// `resume` types the code of a change this session already asked for (`pending_email`).
import { FormModal } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonInput } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { looksLikeEmail } from '../../../frontend/email';
import type { ProfileOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import { reauthRequestOf, useReauthentication } from '../reauth';
import CodeField from './CodeField.vue';
import ReauthModal from './ReauthModal.vue';

type Step = 'address' | 'code';

const props = withDefaults(
  defineProps<{
    profile: Pick<ProfileOut, 'email' | 'pending_email'>;
    mode?: 'change' | 'verify' | 'resume';
  }>(),
  { mode: 'change' },
);

const open = defineModel<boolean>('open', { default: false });

const { t } = useI18n();
const { forDialog } = useErrorText();
const change = useCommand('accounts.email.change');
const verify = useCommand('accounts.email.verify');
const reauth = useReauthentication();

const step = shallowRef<Step>('address');
const address = shallowRef('');
const code = shallowRef('');
/** Where the code went. */
const sentTo = shallowRef('');
/** A wrong code, said under the field. */
const codeError = shallowRef('');
/** Why the dialog went back to the address (the code ran out of tries). */
const notice = shallowRef('');

function reset(): void {
  code.value = '';
  codeError.value = '';
  notice.value = '';
  change.error.value = null;
  verify.error.value = null;
}

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    reset();
    address.value = '';
    if (props.mode === 'verify') {
      sentTo.value = props.profile.email;
      step.value = 'code';
      void send(props.profile.email);
    } else if (props.mode === 'resume' && props.profile.pending_email) {
      sentTo.value = props.profile.pending_email;
      step.value = 'code';
    } else {
      step.value = 'address';
    }
  },
  { immediate: true },
);

/** Mails a code to `email` (after «Confirm it's you» when the server asks); whether it went. */
async function send(email: string): Promise<boolean> {
  try {
    const sent = await reauth.guard(() => change.run({ email }));
    if (sent === undefined) return false;
  } catch {
    return false; // `change.error`: the dialog shows it.
  }
  sentTo.value = email;
  step.value = 'code';
  code.value = '';
  codeError.value = '';
  return true;
}

async function resend(): Promise<void> {
  if (await send(sentTo.value)) void toastSuccess(t('accounts.account.email.resent', { email: sentTo.value }));
}

async function confirm(): Promise<void> {
  codeError.value = '';
  let answer;
  try {
    answer = await verify.run({ code: code.value.trim() });
  } catch {
    return; // `verify.error`: the dialog shows it.
  }
  if (answer.verified) {
    const proven = sentTo.value.toLowerCase() === props.profile.email.toLowerCase();
    void toastSuccess(proven ? t('accounts.account.email.verified') : t('accounts.account.email.changed', { email: answer.profile.email }));
    open.value = false;
  } else if (answer.attempts_left > 0) {
    codeError.value = t('accounts.account.email.wrongCode', { left: answer.attempts_left });
  } else {
    notice.value = t('accounts.account.email.codeSpent');
    address.value = sentTo.value;
    step.value = 'address';
  }
}

function submit(): void {
  notice.value = '';
  if (step.value === 'address') void send(address.value.trim());
  else void confirm();
}

/** What the dialog says on top: why it went back, or the command's refusal (never «Confirm it's you»). */
const dialogError = computed(() => {
  if (notice.value) return { message: notice.value };
  const error = step.value === 'code' ? (verify.error.value ?? change.error.value) : change.error.value;
  return reauthRequestOf(error) ? null : forDialog(error);
});
/** The address step waits for an address that looks like one (audit 2 R-32): a typo never opens «Confirm it's you». */
const incomplete = computed(() => (step.value === 'address' ? !looksLikeEmail(address.value) : !code.value.trim()));
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="email-change"
    :title="step === 'address' ? $t('accounts.account.email.changeTitle') : $t('accounts.account.email.codeTitle')"
    :submit-label="step === 'address' ? $t('accounts.account.email.send') : $t('accounts.account.email.confirm')"
    :submit-icon="step === 'address' ? 'ion:mail-outline' : 'ion:checkmark-outline'"
    :submit-disabled="incomplete"
    :pending="change.pending.value || verify.pending.value"
    :error="dialogError"
    @submit="submit"
  >
    <template #default="{ fieldErrors }">
      <template v-if="step === 'address'">
        <ion-input
          v-model="address"
          data-testid="email-change-address"
          data-autofocus
          mode="md"
          fill="outline"
          type="email"
          inputmode="email"
          autocomplete="email"
          label-placement="floating"
          :label="$t('accounts.account.email.newAddress')"
          :helper-text="$t('accounts.account.email.addressHint')"
          :error-text="fieldErrors.email"
          :class="{ 'ion-invalid': !!fieldErrors.email, 'ion-touched': !!fieldErrors.email }"
        />
      </template>
      <template v-else>
        <p
          class="flow-lead"
          data-testid="email-change-sent"
        >
          {{ $t('accounts.account.email.codeLead', { email: sentTo }) }}
        </p>
        <CodeField
          v-model="code"
          :error="codeError || fieldErrors.code"
        />
        <ion-button
          class="flow-link"
          fill="clear"
          size="small"
          data-testid="email-change-resend"
          :disabled="change.pending.value"
          @click="resend"
        >
          {{ $t('accounts.account.email.resend') }}
        </ion-button>
      </template>
    </template>
  </FormModal>
  <ReauthModal
    :request="reauth.request.value"
    @confirmed="reauth.confirmed"
    @cancel="reauth.cancelled"
  />
</template>

<style scoped>
.flow-lead {
  margin: 0 0 16px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.flow-link {
  --padding-start: 0;
  margin: 8px 0 0;
  text-transform: none;
}
</style>
