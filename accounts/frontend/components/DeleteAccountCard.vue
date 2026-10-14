<script setup lang="ts">
// The danger card of Account → Profile (mockups `account.html` «profile», «Eliminar tu cuenta»; on every surface:
// Google Play asks for it in the apps). It says up front which businesses hold the account — those it owns
// (`can.delete`: transfer or delete them) and those it pays for without owning them (`is_payer`: their owner
// enters their own payment details) — named in one line, each linked to its Settings, and keeps «Delete account»
// off meanwhile. A
// business in its 90 days of deletion holds nobody. Read from `hubs.business.list`, the operation the server reads
// for the same rule (`accounts.services.businesses_holding`); the server decides in the end
// (DeleteAccountDialog shows its 409 too).
import { HubIcon } from '@erplora/ui/shell';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessRowOut, ProfileOut } from '../../../frontend/sdk-types';
import DeleteAccountDialog from './DeleteAccountDialog.vue';

defineProps<{
  profile: Pick<ProfileOut, 'email'>;
}>();

/** The businesses read at once: an account with more is rare, and the server checks all of them anyway. */
const BUSINESS_PAGE = 100;

const { locale } = useI18n();
const live = useLive('hubs.business.list', () => ({ limit: BUSINESS_PAGE, offset: 0 }));
const rows = computed<BusinessRowOut[]>(() => live.data.value?.rows ?? []);
const owned = computed(() => rows.value.filter((row) => row.can.delete));
const paid = computed(() => rows.value.filter((row) => !row.can.delete && row.is_payer && !row.deletion_requested_at));
const held = computed(() => owned.value.length > 0 || paid.value.length > 0);

/**
 * The businesses that hold the account, named in ONE line as the person's language joins them («A, B y C»),
 * each name a link to its Settings: not a stack of links (Ioan, 2026-10-14). The sentence above says what to do.
 */
const heldParts = computed<Array<{ business?: BusinessRowOut; text?: string }>>(() => {
  const list = owned.value.length ? owned.value : paid.value;
  let next = 0;
  return new Intl.ListFormat(locale.value, { type: 'conjunction' })
    .formatToParts(list.map((business) => business.name))
    .map((part) => (part.type === 'element' ? { business: list[next++] } : { text: part.value }));
});
const deleting = shallowRef(false);
</script>

<template>
  <ion-card
    class="danger-card"
    data-testid="profile-danger"
  >
    <ion-card-content class="ion-padding">
      <div class="card-row">
        <div class="card-row__text">
          <h2 class="card-row__title">
            {{ $t('accounts.account.delete.title') }}
          </h2>
          <p
            v-if="owned.length"
            class="card-text"
          >
            {{ $t('accounts.account.delete.owns', owned.length) }}
          </p>
          <p
            v-else-if="paid.length"
            class="card-text"
          >
            {{ $t('accounts.account.delete.pays', paid.length) }}
          </p>
          <p
            v-else
            class="card-text"
          >
            {{ $t('accounts.account.delete.lead') }}
          </p>
          <p
            v-if="held"
            class="held-line"
            data-testid="profile-danger-businesses"
          >
            <template
              v-for="(part, index) in heldParts"
              :key="index"
            >
              <router-link
                v-if="part.business"
                data-testid="profile-danger-business"
                :to="`/businesses/${part.business.id}/settings`"
              >
                {{ part.business.name }}
              </router-link>
              <template v-else>
                {{ part.text }}
              </template>
            </template>
          </p>
        </div>
        <ion-button
          data-testid="profile-delete"
          fill="outline"
          color="danger"
          :disabled="held"
          @click="deleting = true"
        >
          <HubIcon
            slot="start"
            name="lucide:user-x"
          />
          {{ $t('accounts.account.delete.confirm') }}
        </ion-button>
      </div>
    </ion-card-content>
  </ion-card>
  <DeleteAccountDialog
    v-model:open="deleting"
    :profile="profile"
  />
</template>

<style scoped src="./account-card.css"></style>
<style scoped>
.danger-card {
  border: 1px solid color-mix(in oklab, var(--ion-color-danger) 35%, transparent);
}
.danger-card .card-row {
  padding: 0;
}
.held-line {
  margin: 8px 0 0;
  font-size: 0.9rem;
  line-height: 1.5;
}
.held-line a {
  font-weight: 500;
  color: var(--ion-color-primary);
  text-decoration: none;
}
.held-line a:hover,
.held-line a:focus-visible {
  text-decoration: underline;
}
</style>
