<script setup lang="ts">
// «New key» of Account → API keys (mockups `account.html` «keys», README §3b and §6.17): a FormModal with a name
// (required: no placeholder becomes a name, X-17), the permissions the server offers (`ApiKeyListOut.scopes`, at
// least one; none ticked to start, so a key gets only what it needs) and its expiry (30 or 90 days, 90 by default,
// or never). `accounts.apikey.create` asks «Confirm it's you» when the server wants it (ReauthModal), then the
// dialog shows the whole key once (`erps_live_…`) with «Copy» until «I have saved it»; meanwhile a tap outside
// does not close it. The list shows the new key on its own (live).
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonCheckbox, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { ApiKeyCreatedOut, ApiKeyScopeOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import { reauthRequestOf, useReauthentication } from '../reauth';
import ReauthModal from './ReauthModal.vue';

type Expiry = '30' | '90' | 'never';

defineProps<{
  /** The permissions a key may get, labelled by the server in the reader's language. */
  scopes: ApiKeyScopeOut[];
}>();

const open = defineModel<boolean>('open', { default: false });

const EXPIRIES: Expiry[] = ['30', '90', 'never'];
const DAYS: Record<Expiry, 30 | 90 | null> = { '30': 30, '90': 90, never: null };
const EXPIRY_LABEL: Record<Expiry, string> = {
  '30': 'accounts.account.keys.expiries.days30',
  '90': 'accounts.account.keys.expiries.days90',
  never: 'accounts.account.keys.expiries.never',
};

const { t } = useI18n();
const { forDialog } = useErrorText();
const create = useCommand('accounts.apikey.create');
const reauth = useReauthentication();

const name = shallowRef('');
const chosen = shallowRef<string[]>([]);
const expiry = shallowRef<Expiry>('90');
const created = shallowRef<ApiKeyCreatedOut | null>(null);

watch(open, (isOpen) => {
  if (!isOpen) return;
  name.value = '';
  chosen.value = [];
  expiry.value = '90';
  created.value = null;
  create.error.value = null;
});

const incomplete = computed(() => !name.value.trim() || chosen.value.length === 0);
const dialogError = computed(() => (reauthRequestOf(create.error.value) ? null : forDialog(create.error.value)));

function tick(scope: string, event: CustomEvent<{ checked?: boolean }>): void {
  const others = chosen.value.filter((id) => id !== scope);
  chosen.value = event.detail.checked ? [...others, scope] : others;
}

async function submit(): Promise<void> {
  try {
    const answer = await reauth.guard(() =>
      create.run({ name: name.value.trim(), scopes: chosen.value, expires_in_days: DAYS[expiry.value] }),
    );
    if (!answer) return;
    created.value = answer;
    void toastSuccess(t('accounts.account.keys.created', { name: answer.key.name }));
  } catch {
    // `create.error`: the dialog shows it.
  }
}

async function copy(): Promise<void> {
  const secret = created.value?.secret;
  if (!secret) return;
  try {
    await navigator.clipboard.writeText(secret);
    void toastSuccess(t('accounts.account.keys.copied'));
  } catch {
    void toastError(t('accounts.account.keys.copyFailed'));
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="new-key"
    :title="$t('accounts.account.keys.newTitle')"
    :submit-label="$t('accounts.account.keys.create')"
    submit-icon="lucide:key-round"
    :submit-disabled="incomplete"
    :dismiss-on-backdrop="!created"
    :pending="create.pending.value"
    :error="created ? null : dialogError"
    @submit="submit"
  >
    <template #default="{ fieldErrors }">
      <template v-if="created">
        <p class="key-lead">
          {{ $t('accounts.account.keys.copyNow') }}
        </p>
        <div class="secret-field">
          <span class="secret-field__text">
            <span class="secret-field__name">{{ created.key.name }}</span>
            <code
              class="secret-field__value"
              data-testid="new-key-secret"
            >{{ created.secret }}</code>
          </span>
          <ion-button
            data-testid="new-key-copy"
            fill="clear"
            data-autofocus
            :aria-label="$t('accounts.account.keys.copy')"
            @click="copy"
          >
            <HubIcon
              slot="icon-only"
              name="lucide:copy"
            />
          </ion-button>
        </div>
      </template>
      <template v-else>
        <ion-input
          v-model="name"
          data-testid="new-key-name"
          mode="md"
          fill="outline"
          label-placement="floating"
          autocomplete="off"
          :required="true"
          :maxlength="120"
          :label="$t('accounts.account.keys.name')"
          :helper-text="$t('accounts.account.keys.nameHint')"
          :error-text="fieldErrors.name"
          :class="{ 'ion-invalid': !!fieldErrors.name, 'ion-touched': !!fieldErrors.name }"
        />
        <fieldset class="scopes">
          <legend class="scopes__legend">
            {{ $t('accounts.account.keys.permissions') }}
          </legend>
          <ion-checkbox
            v-for="scope in scopes"
            :key="scope.id"
            :data-testid="`new-key-scope-${scope.id}`"
            label-placement="end"
            justify="start"
            :checked="chosen.includes(scope.id)"
            @ion-change="tick(scope.id, $event)"
          >
            {{ scope.label }}
          </ion-checkbox>
          <p
            v-if="fieldErrors.scopes"
            class="scopes__error"
          >
            {{ fieldErrors.scopes }}
          </p>
        </fieldset>
        <ion-select
          data-testid="new-key-expiry"
          mode="md"
          fill="outline"
          interface="popover"
          label-placement="floating"
          :label="$t('accounts.account.keys.expiry')"
          :value="expiry"
          @ion-change="expiry = String($event.detail.value) as Expiry"
        >
          <ion-select-option
            v-for="option in EXPIRIES"
            :key="option"
            :value="option"
          >
            {{ $t(EXPIRY_LABEL[option]) }}
          </ion-select-option>
        </ion-select>
        <InlineFeedback
          class="key-once"
          tone="info"
          icon="lucide:eye"
        >
          {{ $t('accounts.account.keys.once') }}
        </InlineFeedback>
      </template>
    </template>
    <template
      v-if="created"
      #footer
    >
      <ion-button
        data-testid="new-key-done"
        @click="open = false"
      >
        <HubIcon
          slot="start"
          name="ion:checkmark-outline"
        />
        {{ $t('accounts.account.keys.saved') }}
      </ion-button>
    </template>
  </FormModal>
  <ReauthModal
    :request="reauth.request.value"
    @confirmed="reauth.confirmed"
    @cancel="reauth.cancelled"
  />
</template>

<style scoped>
.key-lead {
  margin: 0 0 12px;
  line-height: 1.45;
}
.secret-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 6px 8px 14px;
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.15));
  border-radius: 10px;
  background: var(--ion-color-step-50, rgba(0, 0, 0, 0.02));
}
.secret-field__text {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.secret-field__name {
  font-size: 0.8rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
.secret-field__value {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  overflow-wrap: anywhere;
  user-select: all;
}
.scopes {
  display: grid;
  gap: 10px;
  margin: 18px 0;
  padding: 0;
  border: 0;
}
.scopes__legend {
  margin-bottom: 8px;
  padding: 0;
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 70%, transparent));
}
.scopes__error {
  margin: 0;
  font-size: 0.8rem;
  color: var(--ion-color-danger);
}
.key-once {
  margin-top: 16px;
}
</style>
