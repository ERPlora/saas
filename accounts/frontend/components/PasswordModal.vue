<script setup lang="ts">
// «Change password» of Account → Security (mockups `account.html` «security», «Contraseña»): the current password
// and the new one, over allauth.headless (`account/password/change`; `accounts/doors.py` lets an account with a
// password through). While the new one is typed, a hint of how strong it looks (`../password.ts`); the server's
// validators decide, and allauth's refusals go under their field (`current_password`, `new_password`). A new
// password ends the account's sessions in its businesses (PLAN-SAAS §2.1), so the toast says they will ask to sign
// in again; a change that ends this session too leaves for the sign-in. «Confirm it's you» first if allauth asks.
import { FormModal } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { ApiError, createAllauthClient, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonInputPasswordToggle } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../error-text';
import { passwordStrength } from '../password';
import { reauthRequestOf, useReauthentication } from '../reauth';
import ReauthModal from './ReauthModal.vue';

const props = withDefaults(
  defineProps<{
    /** The account's email: a new password with it inside is weak. */
    email: string;
    /** Where the page goes when the change ended the session (a full load). */
    leave?: (url: string) => void;
  }>(),
  { leave: (url: string) => location.assign(url) },
);

const open = defineModel<boolean>('open', { default: false });

const SIGN_IN = '/login';
const NON_FIELD = '__all__';
/** allauth's codes for a current password that is not the account's. */
const WRONG_CURRENT = new Set(['enter_current_password', 'incorrect_password']);

const { t } = useI18n();
const { text } = useErrorText();
const auth = createAllauthClient(useLiveClient().config);
const reauth = useReauthentication();

const current = shallowRef('');
const next = shallowRef('');
const pending = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

watch(open, (isOpen) => {
  if (!isOpen) return;
  current.value = '';
  next.value = '';
  fields.value = {};
  failure.value = '';
});

const strength = computed(() => passwordStrength(next.value, props.email));
const hint = computed(() => (strength.value === 'empty' ? t('accounts.account.password.hint') : t(`accounts.account.password.strength.${strength.value}`)));
const incomplete = computed(() => !current.value || !next.value);
const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

async function submit(): Promise<void> {
  pending.value = true;
  fields.value = {};
  failure.value = '';
  try {
    const state = await reauth.guard(() => auth.changePassword({ current_password: current.value, new_password: next.value }));
    if (!state) return;
    if (!state.authenticated) {
      props.leave(SIGN_IN);
      return;
    }
    void toastSuccess(t('accounts.account.password.changed'));
    open.value = false;
  } catch (error) {
    if (error instanceof ApiError && error.fields) {
      // allauth's «Please type your current password» reads «Por favor, escriba…» in Spanish: the panel says it
      // in its own words (audit 2 R-26).
      fields.value = WRONG_CURRENT.has(error.code)
        ? { ...error.fields, current_password: t('accounts.account.password.wrongCurrent') }
        : error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else if (!reauthRequestOf(error)) {
      failure.value = error instanceof ApiError ? text(error) : t('accounts.account.errors.unexpected');
    }
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="password-change"
    size="sm"
    submit-icon="lucide:key-round"
    :title="$t('accounts.account.password.title')"
    :submit-label="$t('accounts.account.password.submit')"
    :submit-disabled="incomplete"
    :pending="pending"
    :error="failure ? { message: failure } : null"
    @submit="submit"
  >
    <div class="password-fields">
      <ion-input
        v-model="current"
        data-testid="password-current"
        data-autofocus
        mode="md"
        fill="outline"
        type="password"
        label-placement="floating"
        autocomplete="current-password"
        :label="$t('accounts.account.password.current')"
        :error-text="fields.current_password"
        :class="invalid('current_password')"
      >
        <ion-input-password-toggle slot="end" />
      </ion-input>
      <ion-input
        v-model="next"
        data-testid="password-new"
        mode="md"
        fill="outline"
        type="password"
        label-placement="floating"
        autocomplete="new-password"
        :label="$t('accounts.account.password.new')"
        :helper-text="hint"
        :error-text="fields.new_password"
        :class="[invalid('new_password'), `strength-${strength}`]"
      >
        <ion-input-password-toggle slot="end" />
      </ion-input>
    </div>
  </FormModal>
  <ReauthModal
    :request="reauth.request.value"
    @confirmed="reauth.confirmed"
    @cancel="reauth.cancelled"
  />
</template>

<style scoped>
.password-fields {
  display: grid;
  gap: 14px;
}
</style>
