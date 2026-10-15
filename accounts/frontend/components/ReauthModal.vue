<script setup lang="ts">
// «Confirm it's you» (accounts/README.md, «Reautenticación»): the dialog a command opens when the server wants a
// recent sign-in (`useReauthentication`, `../reauth.ts`). It offers the ways the server sent, the password first:
//   - `reauthenticate`: the password (allauth.headless `auth/reauthenticate`);
//   - `mfa_reauthenticate`: a code of the authenticator app or a recovery code (`auth/2fa/reauthenticate`);
//   - `provider_redirect` with Google: signing in with Google again, a form POST to allauth.headless's provider
//     redirect (as the sign-in page does) that comes back to this same page, where the person does it once more.
// Confirmed → `confirmed` (the page runs its command again). Closed → `cancel`. A wrong password or code stays
// in the dialog, said under its field. Reusable by any page: it only needs the request and the two events.
import { FormModal } from '@erplora/ui/components';
import { ApiError, createAllauthClient, type FieldErrors, type ProviderRedirectForm, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonInputPasswordToggle } from '@ionic/vue';
import { computed, shallowRef, useTemplateRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';

import { useErrorText } from '../error-text';
import type { ReauthRequest } from '../reauth';
import CodeField from './CodeField.vue';

type Way = 'password' | 'code' | 'google';

const props = defineProps<{
  /** What the server asked for; the dialog is open while it is set. */
  request: ReauthRequest | null;
}>();

const emit = defineEmits<{ confirmed: []; cancel: [] }>();

/** allauth's message for the whole form, not one field. */
const NON_FIELD = '__all__';
const GOOGLE = 'google';

const { t } = useI18n();
const route = useRoute();
const { text } = useErrorText();
const auth = createAllauthClient(useLiveClient().config);
const googleRedirect = shallowRef<ProviderRedirectForm | null>(null);
const googleForm = useTemplateRef<HTMLFormElement>('googleForm');

const offered = computed<Way[]>(() => {
  const flows = props.request?.flows ?? [];
  const ways: Way[] = [];
  if (flows.includes('reauthenticate')) ways.push('password');
  if (flows.includes('mfa_reauthenticate')) ways.push('code');
  if (flows.includes('provider_redirect') && props.request?.providers.includes(GOOGLE)) ways.push('google');
  return ways;
});

const way = shallowRef<Way>('password');
const password = shallowRef('');
const code = shallowRef('');
const pending = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');

watch(
  () => props.request,
  (asked) => {
    if (!asked) return;
    way.value = offered.value[0] ?? 'password';
    password.value = '';
    code.value = '';
    fields.value = {};
    failure.value = '';
    googleRedirect.value = auth.providerRedirectForm({ provider: GOOGLE, callbackUrl: route.fullPath, process: 'login' });
  },
  { immediate: true },
);

const open = computed({
  get: () => props.request !== null,
  set: (isOpen: boolean) => {
    if (!isOpen && props.request) emit('cancel');
  },
});

const lead = computed(() => {
  if (way.value === 'code') return t('accounts.reauthenticate.codeLead');
  if (way.value === 'google') return t('accounts.account.reauth.googleLead');
  return t('accounts.account.reauth.passwordLead');
});
const submitLabel = computed(() =>
  way.value === 'google' ? t('accounts.login.continueWithGoogle') : t('accounts.reauthenticate.confirm'),
);
const incomplete = computed(
  () => (way.value === 'password' && !password.value) || (way.value === 'code' && !code.value.trim()),
);
/** The other ways, as links under the field. */
const others = computed(() => offered.value.filter((other) => other !== way.value));
const OTHER_LABEL: Record<Way, string> = {
  password: 'accounts.reauthenticate.usePassword',
  code: 'accounts.reauthenticate.useAuthenticator',
  google: 'accounts.account.reauth.useGoogle',
};
const OTHER_HOOK: Record<Way, string> = { password: 'reauth-use-password', code: 'reauth-use-code', google: 'reauth-use-google' };

function use(other: Way): void {
  way.value = other;
  fields.value = {};
  failure.value = '';
}

async function submit(): Promise<void> {
  if (way.value === 'google') {
    googleForm.value?.submit();
    return;
  }
  pending.value = true;
  fields.value = {};
  failure.value = '';
  try {
    if (way.value === 'code') await auth.mfaReauthenticate(code.value.trim());
    else await auth.reauthenticate(password.value);
    emit('confirmed');
  } catch (error) {
    if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else {
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
    class="ep-reauth-modal"
    testid="reauth-modal"
    size="sm"
    :title="$t('accounts.reauthenticate.title')"
    :submit-label="submitLabel"
    :submit-icon="way === 'google' ? 'ion:logo-google' : 'lucide:lock'"
    :submit-disabled="incomplete"
    :pending="pending"
    :error="failure ? { message: failure } : null"
    @submit="submit"
  >
    <p
      class="reauth-lead"
      data-testid="reauth-lead"
    >
      {{ lead }}
    </p>
    <ion-input
      v-if="way === 'password'"
      v-model="password"
      data-testid="reauth-password"
      data-autofocus
      mode="md"
      fill="outline"
      type="password"
      label-placement="floating"
      autocomplete="current-password"
      :label="$t('accounts.reauthenticate.password')"
      :error-text="fields.password"
      :class="{ 'ion-invalid': !!fields.password, 'ion-touched': !!fields.password }"
    >
      <ion-input-password-toggle slot="end" />
    </ion-input>
    <CodeField
      v-else-if="way === 'code'"
      v-model="code"
      :error="fields.code"
    />
    <div
      v-if="others.length"
      class="reauth-others"
    >
      <ion-button
        v-for="other in others"
        :key="other"
        fill="clear"
        size="small"
        :data-testid="OTHER_HOOK[other]"
        @click="use(other)"
      >
        {{ $t(OTHER_LABEL[other]) }}
      </ion-button>
    </div>
  </FormModal>
  <form
    v-if="googleRedirect && offered.includes('google')"
    ref="googleForm"
    data-testid="reauth-google"
    :method="googleRedirect.method"
    :action="googleRedirect.action"
    hidden
  >
    <input
      v-for="(value, name) in googleRedirect.fields"
      :key="name"
      type="hidden"
      :name="name"
      :value="value"
    >
  </form>
</template>

<style>
/* It opens on top of the dialog that needed it (a new key, a new email): Ionic strips the backdrop and the shadow
   of a second default modal (`core.css`, `.show-modal ~ ion-modal.modal-default`), which left this one glued onto
   the first, both alike. It keeps its own: the first dims behind it. */
ion-modal.modal-default.show-modal ~ ion-modal.modal-default.ep-reauth-modal {
  --backdrop-opacity: var(--ion-backdrop-opacity, 0.4);
  --box-shadow: var(--ep-shadow-modal, 0 18px 50px rgba(0, 0, 0, 0.25));
}
</style>
<style scoped>
.reauth-lead {
  margin: 0 0 16px;
  line-height: 1.45;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 72%, transparent));
}
.reauth-others {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.reauth-others ion-button {
  --padding-start: 0;
  margin: 0;
  text-transform: none;
}
</style>
