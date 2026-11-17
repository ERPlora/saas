<script setup lang="ts">
// «Do you have a promo code?» of the Store: the code is checked with `billing.promo.check` before paying and the
// answer is the model (`v-model`), which the Store hands to the checkout when it is valid. A code grants trial days
// or a discount; an invalid one is said and never blocks the sale. Its styles are the Store's (`.store-promo`).
import { HubIcon } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../../../hubs/frontend/error-text';
import { discountText } from '../discount-text';
import { formatCents } from '../format';
import type { PromoCheckOut } from '../promo-types';

const promo = defineModel<PromoCheckOut | null>({ default: null });

const { t, locale } = useI18n();
const { forDialog } = useErrorText();
const client = useLiveClient();

const promoOpen = shallowRef(false);
const promoTyped = shallowRef('');
const promoPending = shallowRef(false);
const promoError = shallowRef('');

const result = computed(() => {
  if (promoError.value) return promoError.value;
  const answer = promo.value;
  if (!answer?.valid) return t('billing.promo.invalid');
  if (answer.discount === null) return t('billing.promo.valid', { code: answer.code, days: answer.trial_days });
  const said = discountText({ t, money: (cents) => formatCents(cents, locale.value) }, answer.discount);
  return t('billing.promo.validDiscount', { code: answer.code, discount: said });
});

async function applyPromo(): Promise<void> {
  const code = promoTyped.value.trim();
  if (!code) return;
  promoPending.value = true;
  promoError.value = '';
  try {
    promo.value = await client.api.call('billing.promo.check', { code });
  } catch (error) {
    promo.value = null;
    promoError.value = forDialog(error as never)?.message ?? '';
  } finally {
    promoPending.value = false;
  }
}

function removePromo(): void {
  promo.value = null;
  promoTyped.value = '';
}
</script>

<template>
  <div class="store-promo">
    <ion-button
      v-if="!promoOpen"
      fill="clear"
      class="link-button"
      data-testid="store-promo-toggle"
      @click="promoOpen = true"
    >
      <HubIcon
        slot="start"
        name="ion:ticket-outline"
        aria-hidden="true"
      />
      {{ $t('billing.promo.ask') }}
    </ion-button>
    <form
      v-else
      class="store-promo__form"
      novalidate
      @submit.prevent="applyPromo"
    >
      <ion-input
        mode="md"
        fill="outline"
        label-placement="floating"
        autocapitalize="characters"
        :label="$t('billing.promo.label')"
        :value="promoTyped"
        data-testid="store-promo-code"
        @ion-input="promoTyped = String($event.detail.value ?? '')"
      />
      <ion-button
        fill="outline"
        :disabled="promoPending || !promoTyped.trim()"
        data-testid="store-promo-apply"
        @click="applyPromo"
      >
        <HubIcon
          slot="start"
          name="ion:checkmark-outline"
          aria-hidden="true"
        />
        {{ $t('billing.promo.apply') }}
      </ion-button>
      <ion-button
        v-if="promo"
        fill="clear"
        class="btn-neutral"
        data-testid="store-promo-remove"
        @click="removePromo"
      >
        <HubIcon
          slot="start"
          name="ion:close-outline"
          aria-hidden="true"
        />
        {{ $t('billing.promo.remove') }}
      </ion-button>
    </form>
    <p
      v-if="promo || promoError"
      class="store-promo__result"
      :class="{ 'is-invalid': !promo?.valid }"
      role="status"
      data-testid="store-promo-result"
    >
      {{ result }}
    </p>
  </div>
</template>
