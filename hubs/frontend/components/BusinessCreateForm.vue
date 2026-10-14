<script setup lang="ts">
// The sign-up of a business (round 17 §2.3; mockups `launch.html` «first», `businesses.html` «create»):
// the name, the country and, if the person knows it, the business type; under the name, the address
// the name proposes (`hubs.address.propose`, 300 ms after it stops changing). «Create my business»
// runs `hubs.business.create` and hands the new business to the parent (`created`), which shows its
// preparation. One form for the launcher, the empty Businesses and the «Create business» dialog; in the
// dialog the dialog's button submits it (`submitButton: false` + `submit()`).
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { fieldErrors, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessDetailOut, BusinessTypeOut } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import { countryOptions, DEFAULT_COUNTRY } from '../regions';

const props = withDefaults(
  defineProps<{
    /** Paints its own «Create my business» button; off inside a dialog, whose button submits. */
    submitButton?: boolean;
  }>(),
  { submitButton: true },
);

const emit = defineEmits<{
  /** The business exists (being prepared); `typeName` is the type picked, for the preparation's steps. */
  created: [business: BusinessDetailOut, extra: { typeName: string | null }];
  'update:pending': [pending: boolean];
}>();

/** How long the name must stay still before its address is asked for. */
const ADDRESS_DELAY_MS = 300;

const { t, locale } = useI18n();
const client = useLiveClient();
const create = useCommand('hubs.business.create');
const { text } = useErrorText();

const name = shallowRef('');
const country = shallowRef<string>(DEFAULT_COUNTRY);
const businessType = shallowRef('');
const types = shallowRef<BusinessTypeOut[]>([]);
const typesFailed = shallowRef(false);
const address = shallowRef<{ state: 'idle' | 'checking' | 'ready'; host: string }>({ state: 'idle', host: '' });
/** «Write the name» after a submit without one. */
const nameMissing = shallowRef(false);

const countries = computed(() => countryOptions(locale.value));
const errors = computed(() => fieldErrors(create.error.value));
const formError = computed(() => {
  const error = create.error.value;
  return error && Object.keys(errors.value).length === 0 ? text(error) : '';
});
const nameError = computed(() => (nameMissing.value ? t('hubs.create.nameRequired') : errors.value.name ?? ''));

watch(create.pending, (pending) => emit('update:pending', pending));

onMounted(async () => {
  try {
    types.value = (await client.api.call('hubs.business_type.list')).business_types;
  } catch {
    typesFailed.value = true;
  }
});

// ── The address the name proposes ─────────────────────────────────────────────────────────────
let cancelAsk: (() => void) | null = null;
let asked = 0;

async function askAddress(forName: string): Promise<void> {
  const ticket = ++asked;
  try {
    const answer = await client.api.call('hubs.address.propose', { name: forName });
    if (ticket === asked) address.value = { state: 'ready', host: answer.host };
  } catch {
    // The address is only a hint: without it the form still works (the server proposes one).
    if (ticket === asked) address.value = { state: 'idle', host: '' };
  }
}

watch(name, (value) => {
  cancelAsk?.();
  cancelAsk = null;
  const trimmed = value.trim();
  if (!trimmed) {
    asked++;
    address.value = { state: 'idle', host: '' };
    return;
  }
  nameMissing.value = false;
  address.value = { state: 'checking', host: address.value.host };
  cancelAsk = client.schedule(() => void askAddress(trimmed), ADDRESS_DELAY_MS);
});

onBeforeUnmount(() => cancelAsk?.());

// ── Creating ──────────────────────────────────────────────────────────────────────────────────
function onName(event: CustomEvent<{ value?: string | null }>): void {
  name.value = event.detail.value ?? '';
}

async function submit(): Promise<void> {
  if (create.pending.value) return;
  const trimmed = name.value.trim();
  if (!trimmed) {
    nameMissing.value = true;
    return;
  }
  const typeName = types.value.find((type) => type.code === businessType.value)?.name ?? null;
  try {
    const business = await create.run({ name: trimmed, country: country.value, business_type: businessType.value || null });
    void toastSuccess(t('hubs.create.created', { name: business.name }));
    emit('created', business, { typeName });
  } catch {
    // `create.error` holds it: its fields go to the fields, anything else above the button.
  }
}

defineExpose({ submit, pending: create.pending });
</script>

<template>
  <form
    class="create-form"
    novalidate
    @submit.prevent="submit"
  >
    <div class="create-field">
      <ion-input
        data-testid="create-name"
        mode="md"
        fill="outline"
        label-placement="floating"
        autocomplete="organization"
        required
        :label="$t('hubs.create.name')"
        :placeholder="$t('hubs.create.namePlaceholder')"
        :value="name"
        :error-text="nameError || undefined"
        :class="{ 'ion-invalid': !!nameError, 'ion-touched': !!nameError }"
        @ion-input="onName"
        @keydown.enter.prevent="submit"
      />
      <p
        v-if="address.state !== 'idle'"
        class="field-hint"
        :class="{ 'is-ok': address.state === 'ready' }"
        data-testid="create-address"
      >
        <template v-if="address.state === 'ready'">
          <HubIcon name="ion:checkmark-circle-outline" />
          <i18n-t
            keypath="hubs.create.address"
            tag="span"
          >
            <template #host>
              <span class="mono">{{ address.host }}</span>
            </template>
          </i18n-t>
        </template>
        <span v-else>{{ $t('hubs.create.addressChecking') }}</span>
      </p>
    </div>

    <ion-select
      data-testid="create-country"
      class="create-field"
      mode="md"
      fill="outline"
      label-placement="floating"
      interface="popover"
      :label="$t('hubs.create.country')"
      :value="country"
      :error-text="errors.country"
      :class="{ 'ion-invalid': !!errors.country, 'ion-touched': !!errors.country }"
      @ion-change="country = String($event.detail.value ?? DEFAULT_COUNTRY)"
    >
      <ion-select-option
        v-for="option in countries"
        :key="option.value"
        :value="option.value"
      >
        {{ option.label }}
      </ion-select-option>
    </ion-select>

    <div class="create-field">
      <ion-select
        data-testid="create-type"
        mode="md"
        fill="outline"
        label-placement="floating"
        interface="popover"
        :label="$t('hubs.create.type')"
        :placeholder="$t('hubs.create.typeUnknown')"
        :value="businessType || undefined"
        :error-text="errors.business_type"
        :class="{ 'ion-invalid': !!errors.business_type, 'ion-touched': !!errors.business_type }"
        @ion-change="businessType = String($event.detail.value ?? '')"
      >
        <ion-select-option value="">
          {{ $t('hubs.create.typeUnknown') }}
        </ion-select-option>
        <ion-select-option
          v-for="type in types"
          :key="type.code"
          :value="type.code"
        >
          {{ type.name }}
        </ion-select-option>
      </ion-select>
      <p
        class="field-hint"
        data-testid="create-type-hint"
      >
        {{ typesFailed ? $t('hubs.create.typesFailed') : $t('hubs.create.typeHint') }}
      </p>
    </div>

    <InlineFeedback
      v-if="formError"
      tone="danger"
      data-testid="create-error"
    >
      {{ formError }}
    </InlineFeedback>

    <ion-button
      v-if="props.submitButton"
      data-testid="create-submit"
      expand="block"
      size="large"
      :disabled="create.pending.value"
      @click="submit"
    >
      <ion-spinner
        v-if="create.pending.value"
        slot="start"
        name="crescent"
        aria-hidden="true"
      />
      <HubIcon
        v-else
        slot="start"
        name="ion:add-outline"
      />
      {{ $t('hubs.create.submit') }}
    </ion-button>
  </form>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
.create-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.field-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 2px 0;
  font-size: 0.8rem;
  line-height: 1.4;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.field-hint.is-ok {
  color: var(--ep-success-on-tint, var(--ion-color-success-shade, var(--ion-color-success)));
}
.field-hint .mono {
  font-family: var(--font-mono, ui-monospace, monospace);
}
</style>
