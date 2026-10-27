<script setup lang="ts">
// «Delete account» (mockups `account.html`, the danger card of Profile; GDPR art. 17, and Google Play asks for it
// inside the apps, so it shows on every surface): a ConfirmDialog that says what goes and waits for the account's
// email typed, then `accounts.profile.delete`. A business the account owns or pays for holds it (409
// `accounts.owns_businesses` / `accounts.pays_businesses`, with `businesses`): the dialog names each one with a
// link to its Settings, where it is transferred or deleted. The server may ask «Confirm it's you» first
// (ReauthModal). Deleted, every session has ended: the page leaves for the public web with a full load.
import { ConfirmDialog, InlineFeedback } from '@erplora/ui/components';
import { ApiError, useCommand } from '@erplora/ui/sdk';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { ProfileOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import { BUSINESSES } from '../paths';
import { reauthRequestOf, useReauthentication } from '../reauth';
import ReauthModal from './ReauthModal.vue';

interface HoldingBusiness {
  id: string;
  name: string;
}

const props = withDefaults(
  defineProps<{
    profile: Pick<ProfileOut, 'email'>;
    /** Where the page goes once the account is gone (a full load: the session ended with it). */
    leave?: (url: string) => void;
  }>(),
  { leave: (url: string) => location.assign(url) },
);

const open = defineModel<boolean>('open', { default: false });

/** The codes of the 409 that names the businesses holding the account. */
const HELD = new Set(['accounts.owns_businesses', 'accounts.pays_businesses']);
/** Where the person lands once the account is gone: the public web. */
const AFTER_DELETION = '/';

const { t } = useI18n();
const { forDialog } = useErrorText();
const remove = useCommand('accounts.profile.delete');
const reauth = useReauthentication();
const blocked = shallowRef<{ message: string; businesses: HoldingBusiness[] } | null>(null);

watch(open, (isOpen) => {
  if (!isOpen) return;
  blocked.value = null;
  remove.error.value = null;
});

function businessesOf(error: ApiError): HoldingBusiness[] {
  const raw = error.details.businesses;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is HoldingBusiness => typeof item?.id === 'string' && typeof item?.name === 'string',
  );
}

async function confirm(): Promise<void> {
  blocked.value = null;
  try {
    const done = await reauth.guard(() => remove.run({}));
    if (done?.deleted) props.leave(AFTER_DELETION);
  } catch (error) {
    if (error instanceof ApiError && HELD.has(error.code)) {
      blocked.value = { message: error.message, businesses: businessesOf(error) };
    }
  }
}

/** On top of the dialog: any refusal but «Confirm it's you» (its own dialog) and the businesses (named below). */
const dialogError = computed(() => {
  const error = remove.error.value;
  if (blocked.value || reauthRequestOf(error)) return null;
  return forDialog(error);
});
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    testid="delete-account"
    size="md"
    confirm-icon="lucide:user-x"
    :title="t('accounts.account.delete.title')"
    :confirm-label="t('accounts.account.delete.confirm')"
    :require-text="profile.email"
    :require-text-label="t('accounts.account.delete.typeEmail')"
    :pending="remove.pending.value"
    :error="dialogError"
    @confirm="confirm"
  >
    <p class="delete-text">
      {{ t('accounts.account.delete.message') }}
    </p>
    <InlineFeedback
      v-if="blocked"
      class="delete-blocked"
      tone="warning"
      data-testid="delete-account-blocked"
      :heading="blocked.message"
    >
      <ul class="delete-businesses">
        <li
          v-for="business in blocked.businesses"
          :key="business.id"
        >
          <router-link
            data-testid="delete-account-business"
            :to="`${BUSINESSES}/${business.id}/settings`"
            @click="open = false"
          >
            {{ business.name }}
          </router-link>
        </li>
      </ul>
    </InlineFeedback>
  </ConfirmDialog>
  <ReauthModal
    :request="reauth.request.value"
    @confirmed="reauth.confirmed"
    @cancel="reauth.cancelled"
  />
</template>

<style scoped>
.delete-text {
  margin: 0 0 12px;
  font-size: 0.9rem;
  line-height: 1.5;
}
.delete-blocked {
  margin-bottom: 12px;
}
.delete-businesses {
  margin: 6px 0 0;
  padding-inline-start: 1.1rem;
}
.delete-businesses a {
  color: var(--ion-color-primary);
  font-weight: 500;
}
</style>
