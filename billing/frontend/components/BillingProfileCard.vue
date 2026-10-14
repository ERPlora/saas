<script setup lang="ts">
// Billing → Payment details: the billing details of one payer (mockups `billing.html` «payment»; README §3 and
// §4; `BillingProfile`): who the invoices of its businesses are made out to — name, tax ID, address, email —
// and which businesses it pays. Read with `hubs.billing_profile.get` through the first of them (one payer,
// one set of details) and edited in BillingProfileModal, on every surface: fiscal data is not selling. A
// failure says why, with «Retry».
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonSkeletonText } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../../../hubs/frontend/error-text';
import type { BillingProfileOut, InvoiceBusinessOut } from '../../../frontend/sdk-types';
import BillingProfileModal from './BillingProfileModal.vue';

const props = defineProps<{
  /** The businesses this payer pays. */
  businesses: InvoiceBusinessOut[];
}>();

const { locale } = useI18n();
const { text } = useErrorText();
const client = useLiveClient();

const profile = shallowRef<BillingProfileOut | null>(null);
const failure = shallowRef('');
const editing = shallowRef(false);
const hubId = computed(() => props.businesses.find((business) => business.id)?.id ?? null);

async function load(): Promise<void> {
  const id = hubId.value;
  if (!id) return;
  failure.value = '';
  try {
    profile.value = await client.api.call('hubs.billing_profile.get', { hub_id: id });
  } catch (error) {
    console.error('billing: the billing details could not be loaded', error);
    failure.value = text(error as never);
  }
}
void load();

const pays = computed(() =>
  new Intl.ListFormat(locale.value, { style: 'long', type: 'conjunction' }).format(props.businesses.map((business) => business.name)),
);
const address = computed(() => {
  const now = profile.value;
  if (!now) return '';
  const place = [now.billing_postal_code, now.billing_city].filter(Boolean).join(' ');
  return [now.billing_address, place].filter(Boolean).join(', ');
});
const empty = computed(() => !!profile.value && !profile.value.billing_name && !profile.value.tax_id && !address.value);
</script>

<template>
  <ion-card>
    <ion-card-content class="ion-padding">
      <div class="page-eyebrow">
        {{ $t('billing.payment.profile.title') }}
      </div>
      <InlineFeedback
        v-if="failure"
        class="profile-error"
        tone="danger"
        data-testid="profile-error"
      >
        {{ failure }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="profile-retry"
            @click="load"
          >
            <HubIcon
              slot="start"
              name="ion:refresh-outline"
            />
            {{ $t('billing.payment.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <div
        v-else-if="!profile"
        aria-busy="true"
      >
        <ion-skeleton-text
          animated
          style="width: 70%; height: 20px; margin-top: 14px"
        />
        <ion-skeleton-text
          animated
          style="width: 50%; height: 14px; margin-top: 10px"
        />
      </div>
      <template v-else>
        <p
          v-if="empty"
          class="card-text"
          data-testid="profile-empty"
        >
          {{ $t('billing.payment.profile.empty') }}
        </p>
        <template v-else>
          <h2
            class="card-title profile-name"
            data-testid="profile-name"
          >
            {{ profile.billing_name }}
          </h2>
          <dl class="kv">
            <div v-if="profile.tax_id">
              <dt>{{ $t('billing.payment.profile.taxId') }}</dt>
              <dd>{{ profile.tax_id }}</dd>
            </div>
            <div v-if="address">
              <dt>{{ $t('billing.payment.profile.address') }}</dt>
              <dd>{{ address }}</dd>
            </div>
            <div v-if="profile.billing_email">
              <dt>{{ $t('billing.payment.profile.email') }}</dt>
              <dd>{{ profile.billing_email }}</dd>
            </div>
            <div>
              <dt>{{ $t('billing.payment.profile.pays') }}</dt>
              <dd>{{ pays }}</dd>
            </div>
          </dl>
        </template>
        <div class="card-actions">
          <ion-button
            fill="outline"
            data-testid="profile-edit"
            @click="editing = true"
          >
            <HubIcon
              slot="start"
              name="lucide:pencil"
            />
            {{ $t('billing.payment.profile.edit') }}
          </ion-button>
        </div>
        <BillingProfileModal
          v-model:open="editing"
          :businesses="businesses"
          :profile="profile"
          @saved="profile = $event"
        />
      </template>
    </ion-card-content>
  </ion-card>
</template>

<style scoped src="../../../hubs/frontend/components/panel-card.css"></style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
<style scoped>
.profile-name {
  margin-top: 12px;
}
.profile-error {
  margin-top: 12px;
}
.kv dd {
  overflow-wrap: anywhere;
}
</style>
