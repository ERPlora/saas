<script lang="ts">
/** The payer as the form edits it (`hubs.BillingProfileIn` without the business). */
export interface BillingDetailsDraft {
  billing_name: string;
  tax_id: string;
  billing_address: string;
  billing_city: string;
  billing_postal_code: string;
  billing_country: string;
  billing_email: string;
  same_as_business: boolean;
}
</script>

<script setup lang="ts">
// Who ERPlora invoices for a business (PLAN-SAAS §3.1; mockups `store.html`, the checkout's note): asked
// once, before the first payment, inside the checkout dialog — legal name, tax ID (the server checks it in
// VIES), address, city, postal code (five digits in Spain: it decides the tax) and country, or «use the
// business’s name and country» (the server copies them). Only the fields; the dialog saves them with
// `hubs.billing_profile.update`, and a 422 puts each message under its field. Country is an `ion-select`.
import { IonCheckbox, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { countryOptions } from '../../../hubs/frontend/regions';

defineProps<{
  /** The server's message per field (a 422's `fields`). */
  fieldErrors: Readonly<Record<string, string>>;
}>();

const draft = defineModel<BillingDetailsDraft>({ required: true });

const { locale } = useI18n();
const countries = computed(() => countryOptions(locale.value));

/** What is typed, ahead of the parent's copy: two fields changed in one tick both count. */
const local = shallowRef<BillingDetailsDraft>({ ...draft.value });
watch(draft, (value) => {
  local.value = { ...value };
});

function set<K extends keyof BillingDetailsDraft>(key: K, value: BillingDetailsDraft[K]): void {
  local.value = { ...local.value, [key]: value };
  draft.value = local.value;
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <div class="details-form">
    <p class="details-form__intro">
      {{ $t('billing.details.intro') }}
    </p>
    <ion-checkbox
      label-placement="end"
      justify="start"
      :checked="local.same_as_business"
      data-testid="details-same"
      @ion-change="set('same_as_business', !!$event.detail.checked)"
    >
      {{ $t('billing.details.same') }}
    </ion-checkbox>
    <ion-input
      v-if="!local.same_as_business"
      mode="md"
      fill="outline"
      label-placement="floating"
      autocomplete="organization"
      :label="$t('billing.details.name')"
      :value="local.billing_name"
      :error-text="fieldErrors.billing_name"
      :class="{ 'ion-invalid ion-touched': !!fieldErrors.billing_name }"
      data-testid="details-name"
      @ion-input="set('billing_name', text($event.detail.value))"
    />
    <ion-input
      mode="md"
      fill="outline"
      label-placement="floating"
      :label="$t('billing.details.taxId')"
      :helper-text="$t('billing.details.taxIdHint')"
      :value="local.tax_id"
      :error-text="fieldErrors.tax_id"
      :class="{ 'ion-invalid ion-touched': !!fieldErrors.tax_id }"
      data-testid="details-tax-id"
      @ion-input="set('tax_id', text($event.detail.value))"
    />
    <ion-input
      mode="md"
      fill="outline"
      label-placement="floating"
      autocomplete="street-address"
      :label="$t('billing.details.address')"
      :value="local.billing_address"
      :error-text="fieldErrors.billing_address"
      :class="{ 'ion-invalid ion-touched': !!fieldErrors.billing_address }"
      data-testid="details-address"
      @ion-input="set('billing_address', text($event.detail.value))"
    />
    <div class="details-form__row">
      <ion-input
        mode="md"
        fill="outline"
        label-placement="floating"
        autocomplete="address-level2"
        :label="$t('billing.details.city')"
        :value="local.billing_city"
        :error-text="fieldErrors.billing_city"
        :class="{ 'ion-invalid ion-touched': !!fieldErrors.billing_city }"
        data-testid="details-city"
        @ion-input="set('billing_city', text($event.detail.value))"
      />
      <ion-input
        mode="md"
        fill="outline"
        label-placement="floating"
        autocomplete="postal-code"
        inputmode="numeric"
        :label="$t('billing.details.postalCode')"
        :value="local.billing_postal_code"
        :error-text="fieldErrors.billing_postal_code"
        :class="{ 'ion-invalid ion-touched': !!fieldErrors.billing_postal_code }"
        data-testid="details-postal-code"
        @ion-input="set('billing_postal_code', text($event.detail.value))"
      />
    </div>
    <ion-select
      v-if="!local.same_as_business"
      mode="md"
      fill="outline"
      interface="popover"
      label-placement="floating"
      :label="$t('billing.details.country')"
      :value="local.billing_country"
      :error-text="fieldErrors.billing_country"
      :class="{ 'ion-invalid ion-touched': !!fieldErrors.billing_country }"
      data-testid="details-country"
      @ion-change="set('billing_country', text($event.detail.value))"
    >
      <ion-select-option
        v-for="country in countries"
        :key="country.value"
        :value="country.value"
      >
        {{ country.label }}
      </ion-select-option>
    </ion-select>
    <ion-input
      mode="md"
      fill="outline"
      type="email"
      label-placement="floating"
      autocomplete="email"
      :label="$t('billing.details.email')"
      :value="local.billing_email"
      :error-text="fieldErrors.billing_email"
      :class="{ 'ion-invalid ion-touched': !!fieldErrors.billing_email }"
      data-testid="details-email"
      @ion-input="set('billing_email', text($event.detail.value))"
    />
  </div>
</template>

<style scoped>
.details-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.details-form__intro {
  margin: 0;
  font-size: 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.details-form__row {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
}
@media (max-width: 479px) {
  .details-form__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
