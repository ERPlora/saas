<script setup lang="ts">
// The Settings of a business, «General» (mockups `business.html` «settings»): what the panel shows of
// it — name, country, time zone and language (`hubs.business.update` sends only what changed; the
// receipts' data is edited inside the business) — and its web address, with «Copy» and, for the owner,
// «Change address» (HUBS-F16, AddressDialog). «Save changes» waits for a change; a change made elsewhere arrives live and
// refreshes the fields unless the person is editing them. Once the business is ready its country is
// read-only (`country_locked`: its invoices belong to one country; the server refuses it with 409
// `hubs.country_locked`, said above the button).
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { fieldErrors, useCommand } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonInput, IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed, reactive, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BusinessDetailOut, BusinessUpdateIn } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';
import { countryName, countryOptions, timeZoneOptions } from '../regions';
import AddressDialog from './AddressDialog.vue';
import CopyField from './CopyField.vue';

type Editable = Pick<BusinessDetailOut, 'name' | 'country' | 'timezone' | 'language'>;

const props = defineProps<{
  business: Pick<BusinessDetailOut, 'id' | 'slug' | 'host' | 'status' | 'country_locked'> &
    Editable & { can?: Pick<BusinessDetailOut['can'], 'change_address'> };
}>();

const changingAddress = shallowRef(false);

const LANGUAGES = ['en', 'es'] as const;

const { t, locale } = useI18n();
const update = useCommand('hubs.business.update');
const { text } = useErrorText();

const saved = (): Editable => ({
  name: props.business.name,
  country: props.business.country,
  timezone: props.business.timezone,
  language: props.business.language,
});
const form = reactive<Editable>(saved());

const changes = computed(() => {
  const was = saved();
  const out: Partial<Editable> = {};
  if (form.name.trim() !== was.name) out.name = form.name.trim();
  if (form.country !== was.country) out.country = form.country;
  if (form.timezone !== was.timezone) out.timezone = form.timezone;
  if (form.language !== was.language) out.language = form.language;
  return out;
});
const dirty = computed(() => Object.keys(changes.value).length > 0);
const locked = computed(() => props.business.status === 'deleting');

// The business as the server has it, whenever it changes and the person is not in the middle of an edit.
watch(
  () => saved(),
  (now, before) => {
    const editing = (Object.keys(now) as Array<keyof Editable>).some((key) => form[key] !== before[key]);
    if (!editing && !update.pending.value) Object.assign(form, now);
  },
  { deep: true },
);

const countries = computed(() => countryOptions(locale.value));
const zones = computed(() => timeZoneOptions(locale.value, props.business.timezone));
const errors = computed(() => fieldErrors(update.error.value));
const formError = computed(() => (update.error.value && !Object.keys(errors.value).length ? text(update.error.value) : ''));

async function save(): Promise<void> {
  if (!dirty.value || update.pending.value) return;
  try {
    const answer = await update.run({ id: props.business.id, ...changes.value } as BusinessUpdateIn);
    Object.assign(form, { name: answer.name, country: answer.country, timezone: answer.timezone, language: answer.language });
    void toastSuccess(t('hubs.settings.saved'));
  } catch {
    // `update.error`: its fields on the fields, anything else above the button.
  }
}

const value = (event: CustomEvent<{ value?: unknown }>) => String(event.detail.value ?? '');
</script>

<template>
  <ion-card data-testid="settings-general">
    <ion-card-content class="ion-padding">
      <h2 class="card-title">
        {{ $t('hubs.settings.title') }}
      </h2>
      <p class="card-text">
        {{ $t('hubs.settings.lead') }}
      </p>
      <form
        class="settings-form"
        novalidate
        @submit.prevent="save"
      >
        <div class="settings-grid">
          <ion-input
            data-testid="settings-name"
            mode="md"
            fill="outline"
            label-placement="floating"
            autocomplete="organization"
            :label="$t('hubs.settings.name')"
            :value="form.name"
            :disabled="locked"
            :error-text="errors.name"
            :class="{ 'ion-invalid': !!errors.name, 'ion-touched': !!errors.name }"
            @ion-input="form.name = value($event)"
          />
          <!-- Once ready, the country is read-only text with its reason under it, not a disabled select (R-31). -->
          <div
            v-if="business.country_locked"
            class="readonly-country"
            role="group"
            aria-labelledby="settings-country-label"
            data-testid="settings-country"
          >
            <span
              id="settings-country-label"
              class="readonly-country__label"
            >{{ $t('hubs.settings.country') }}</span>
            <span class="readonly-country__value">{{ countryName(form.country, locale) }}</span>
            <p
              class="field-hint"
              data-testid="settings-country-locked"
            >
              {{ $t('hubs.settings.countryLocked') }}
            </p>
          </div>
          <ion-select
            v-else
            data-testid="settings-country"
            mode="md"
            fill="outline"
            label-placement="floating"
            interface="popover"
            :label="$t('hubs.settings.country')"
            :value="form.country"
            :disabled="locked"
            :error-text="errors.country"
            :class="{ 'ion-invalid': !!errors.country, 'ion-touched': !!errors.country }"
            @ion-change="form.country = value($event)"
          >
            <ion-select-option
              v-for="option in countries"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </ion-select-option>
          </ion-select>
          <ion-select
            data-testid="settings-timezone"
            mode="md"
            fill="outline"
            label-placement="floating"
            interface="popover"
            :label="$t('hubs.settings.timezone')"
            :value="form.timezone"
            :disabled="locked"
            :error-text="errors.timezone"
            :class="{ 'ion-invalid': !!errors.timezone, 'ion-touched': !!errors.timezone }"
            @ion-change="form.timezone = value($event)"
          >
            <ion-select-option
              v-for="option in zones"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </ion-select-option>
          </ion-select>
          <ion-select
            data-testid="settings-language"
            mode="md"
            fill="outline"
            label-placement="floating"
            interface="popover"
            :label="$t('hubs.settings.language')"
            :value="form.language"
            :disabled="locked"
            :error-text="errors.language"
            :class="{ 'ion-invalid': !!errors.language, 'ion-touched': !!errors.language }"
            @ion-change="form.language = value($event)"
          >
            <ion-select-option
              v-for="language in LANGUAGES"
              :key="language"
              :value="language"
            >
              {{ $t(`hubs.settings.languages.${language}`) }}
            </ion-select-option>
          </ion-select>
        </div>

        <p class="field-label">
          {{ $t('hubs.settings.address') }}
        </p>
        <div class="address-row">
          <CopyField
            class="address-row__field"
            :value="business.host"
            :label="$t('hubs.settings.address')"
          />
          <ion-button
            v-if="business.can?.change_address"
            data-testid="settings-change-address"
            fill="outline"
            @click="changingAddress = true"
          >
            <HubIcon
              slot="start"
              name="ion:create-outline"
              aria-hidden="true"
            />
            {{ $t('hubs.settings.changeAddress') }}
          </ion-button>
        </div>

        <InlineFeedback
          v-if="formError"
          tone="danger"
          class="ion-margin-top"
          data-testid="settings-error"
        >
          {{ formError }}
        </InlineFeedback>

        <div class="card-actions settings-actions">
          <ion-button
            data-testid="settings-save"
            :disabled="!dirty || locked || update.pending.value"
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
              name="ion:checkmark-outline"
              aria-hidden="true"
            />
            {{ $t('hubs.settings.save') }}
          </ion-button>
          <span
            v-if="!dirty"
            class="settings-hint"
            data-testid="settings-save-hint"
          >{{ $t('hubs.settings.saveHint') }}</span>
        </div>
      </form>
    </ion-card-content>
    <AddressDialog
      v-if="business.can?.change_address"
      v-model:open="changingAddress"
      :business="{ id: business.id, slug: business.slug, host: business.host }"
    />
  </ion-card>
</template>

<style scoped src="./buttons.css"></style>
<style scoped src="./panel-card.css"></style>
<style scoped>
.settings-form {
  margin-top: 16px;
}
.settings-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(0, 1fr);
}
@media (min-width: 720px) {
  .settings-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
/* Read-only once the business is ready (audit 2 R-31): the country as text, its reason under it. */
.readonly-country {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-height: 56px;
  padding: 0 2px;
}
.readonly-country__label {
  font-size: 0.78rem;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.readonly-country__value {
  font-size: 1rem;
  color: var(--ion-text-color);
}
.readonly-country .field-hint {
  margin-top: 4px;
}
.field-hint {
  margin: 8px 2px 0;
  font-size: 0.8rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.field-label {
  margin: 18px 2px 6px;
  font-size: 0.85rem;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.settings-actions {
  align-items: center;
}
.address-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}
.address-row__field {
  flex: 1 1 260px;
  min-width: 0;
}
.settings-hint {
  font-size: 0.82rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
</style>
