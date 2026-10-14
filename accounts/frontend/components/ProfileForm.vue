<script setup lang="ts">
// Account → Profile, «Your details» (mockups `account.html` «profile»): the avatar with «Change photo»
// (PhotoPicker), first and last name (`accounts.profile.update`, «Save changes» waits for a change and says
// «Changes saved»), and the email the account signs in with, read here and changed only with its code
// (EmailChangeFlow): «Change»; «Verify» for an address never proven; and, while a change waits for its code,
// a notice to type it. The names follow the account when it changes elsewhere, unless the person is typing.
import { InlineFeedback, StatusPill, UserAvatar } from '@erplora/ui/components';
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonInput, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { ProfileOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import EmailChangeFlow from './EmailChangeFlow.vue';
import PhotoPicker from './PhotoPicker.vue';

const props = defineProps<{
  profile: ProfileOut;
}>();

const { t } = useI18n();
const { text } = useErrorText();
const update = useCommand('accounts.profile.update');

const firstName = shallowRef(props.profile.first_name);
const lastName = shallowRef(props.profile.last_name);
const dirty = computed(() => firstName.value !== props.profile.first_name || lastName.value !== props.profile.last_name);
/** The per-field messages of the last refusal (a 422). */
const fieldErrors = computed(() => (update.error.value?.status === 422 ? (update.error.value.fields ?? {}) : {}));

/** What the names were when the page last took them from the account: typing is what differs from it. */
let shown = { first: props.profile.first_name, last: props.profile.last_name };
watch(
  () => [props.profile.first_name, props.profile.last_name] as const,
  ([first, last]) => {
    const typing = firstName.value !== shown.first || lastName.value !== shown.last;
    shown = { first, last };
    if (typing) return;
    firstName.value = first;
    lastName.value = last;
  },
);

async function save(): Promise<void> {
  try {
    const saved = await update.run({ first_name: firstName.value.trim(), last_name: lastName.value.trim() });
    shown = { first: saved.first_name, last: saved.last_name };
    firstName.value = saved.first_name;
    lastName.value = saved.last_name;
    void toastSuccess(t('accounts.account.profile.saved'));
  } catch {
    if (update.error.value?.status !== 422) void toastError(text(update.error.value));
  }
}

const emailMode = shallowRef<'change' | 'verify' | 'resume'>('change');
const emailOpen = shallowRef(false);
function openEmail(mode: 'change' | 'verify' | 'resume'): void {
  emailMode.value = mode;
  emailOpen.value = true;
}
</script>

<template>
  <ion-card data-testid="profile-card">
    <ion-card-content class="ion-padding">
      <h2 class="card-title">
        {{ $t('accounts.account.profile.heading') }}
      </h2>
      <div class="avatar-row">
        <UserAvatar
          data-testid="profile-avatar"
          size="xl"
          :name="profile.full_name"
          :email="profile.email"
          :src="profile.photo"
        />
        <PhotoPicker :profile="profile" />
      </div>
      <div class="field-grid cols-2">
        <ion-input
          v-model="firstName"
          data-testid="profile-first-name"
          mode="md"
          fill="outline"
          label-placement="floating"
          autocomplete="given-name"
          :maxlength="150"
          :label="$t('accounts.account.profile.firstName')"
          :error-text="fieldErrors.first_name"
          :class="{ 'ion-invalid': !!fieldErrors.first_name, 'ion-touched': !!fieldErrors.first_name }"
        />
        <ion-input
          v-model="lastName"
          data-testid="profile-last-name"
          mode="md"
          fill="outline"
          label-placement="floating"
          autocomplete="family-name"
          :maxlength="150"
          :label="$t('accounts.account.profile.lastName')"
          :error-text="fieldErrors.last_name"
          :class="{ 'ion-invalid': !!fieldErrors.last_name, 'ion-touched': !!fieldErrors.last_name }"
        />
      </div>

      <span
        id="profile-email-label"
        class="field-label"
      >{{ $t('accounts.account.profile.email') }}</span>
      <div
        class="readonly-field"
        role="group"
        aria-labelledby="profile-email-label"
      >
        <span
          class="readonly-field__value"
          data-testid="profile-email"
        >
          {{ profile.email }}
          <StatusPill
            v-if="!profile.email_verified"
            data-testid="profile-email-unverified"
            tone="warning"
            size="sm"
            :label="$t('accounts.account.profile.unverified')"
          />
        </span>
        <span class="email-actions">
          <ion-button
            v-if="!profile.email_verified"
            data-testid="profile-email-verify"
            fill="clear"
            size="small"
            @click="openEmail('verify')"
          >
            <HubIcon
              slot="start"
              name="ion:checkmark-circle-outline"
              aria-hidden="true"
            />
            {{ $t('accounts.account.profile.verify') }}
          </ion-button>
          <ion-button
            data-testid="profile-email-change"
            fill="clear"
            size="small"
            :aria-label="$t('accounts.account.profile.changeEmail')"
            @click="openEmail('change')"
          >
            <HubIcon
              slot="start"
              name="lucide:pencil"
              aria-hidden="true"
            />
            {{ $t('accounts.account.profile.change') }}
          </ion-button>
        </span>
      </div>
      <InlineFeedback
        v-if="profile.pending_email"
        class="email-pending"
        tone="info"
        icon="ion:mail-outline"
        data-testid="profile-email-pending"
      >
        {{ $t('accounts.account.profile.pending', { email: profile.pending_email }) }}
        <template #actions>
          <ion-button
            data-testid="profile-email-pending-code"
            size="small"
            fill="outline"
            @click="openEmail('resume')"
          >
            {{ $t('accounts.account.profile.typeCode') }}
          </ion-button>
        </template>
      </InlineFeedback>

      <div class="card-actions">
        <ion-button
          data-testid="profile-save"
          :disabled="!dirty || update.pending.value"
          @click="save"
        >
          <ion-spinner
            v-if="update.pending.value"
            slot="start"
            name="crescent"
            aria-hidden="true"
          />
          <HubIcon
            v-else
            slot="start"
            name="lucide:save"
            aria-hidden="true"
          />
          {{ $t('accounts.account.profile.save') }}
        </ion-button>
        <span
          v-if="!dirty"
          class="hint"
        >{{ $t('accounts.account.profile.saveHint') }}</span>
      </div>
    </ion-card-content>
  </ion-card>
  <EmailChangeFlow
    v-model:open="emailOpen"
    :profile="profile"
    :mode="emailMode"
  />
</template>

<style scoped src="./account-card.css"></style>
<style scoped>
.avatar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
  margin-top: 16px;
}
.readonly-field__value {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.email-actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}
.email-actions ion-button {
  margin: 0;
}
.email-pending {
  margin-top: 12px;
}
</style>
