<script setup lang="ts">
// «Change address» (HUBS-F16; PLAN-SAAS §1.1, round 2026-10-15b): the owner gives the business another web
// address. A FormModal (a form is a sheet, a confirmation a card) that starts from the current address, shows
// the host it gives as the person types (lowercase, trimmed: what the server checks) and says what follows:
// devices and erplora.com follow it, the old address stops opening the business, and nobody else can take
// the old one. `hubs.business.change_address` checks it as the Hub does; a 409 (taken, reserved) stays in the
// dialog, a 422 goes on the field.
import { FormModal } from '@erplora/ui/components';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useErrorText } from '../error-text';

const props = defineProps<{
  business: { id: string; slug: string; host: string };
}>();

const open = defineModel<boolean>('open', { default: false });

const { t } = useI18n();
const { forDialog } = useErrorText();
const change = useCommand('hubs.business.change_address');

const slug = shallowRef(props.business.slug);
const wanted = computed(() => slug.value.trim().toLowerCase());
/** The host is the address plus what follows it today (`.erplora.com`, or `.localhost:8000` in development). */
const suffix = computed(() =>
  props.business.host.startsWith(props.business.slug) ? props.business.host.slice(props.business.slug.length) : '',
);
const host = computed(() => `${wanted.value}${suffix.value}`);
const changed = computed(() => wanted.value !== '' && wanted.value !== props.business.slug);

const consequences = computed(() => [
  { text: t('hubs.addressDialog.consequenceDevices'), icon: 'ion:phone-portrait-outline' },
  { text: t('hubs.addressDialog.consequenceOld'), icon: 'ion:qr-code-outline' },
  { text: t('hubs.addressDialog.consequenceKept'), icon: 'ion:lock-closed-outline' },
]);

watch(open, (isOpen) => {
  if (!isOpen) return;
  slug.value = props.business.slug;
  change.error.value = null;
});

async function submit(): Promise<void> {
  if (!changed.value) return;
  try {
    const moved = await change.run({ id: props.business.id, slug: wanted.value });
    void toastSuccess(t('hubs.addressDialog.changed', { host: moved.host }));
    open.value = false;
  } catch {
    // `change.error`: the dialog shows it (a 422 on the field).
  }
}

const value = (event: CustomEvent<{ value?: unknown }>) => String(event.detail.value ?? '');
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="address-dialog"
    size="md"
    :title="$t('hubs.addressDialog.title')"
    :submit-label="$t('hubs.addressDialog.submit')"
    submit-icon="ion:globe-outline"
    :pending="change.pending.value"
    :error="forDialog(change.error.value)"
    :submit-disabled="!changed"
    @submit="submit"
  >
    <template #default="{ fieldErrors }">
      <div class="address-fields">
        <ion-input
          data-testid="address-dialog-slug"
          data-autofocus
          mode="md"
          fill="outline"
          label-placement="floating"
          autocomplete="off"
          autocapitalize="off"
          inputmode="url"
          :spellcheck="false"
          :maxlength="63"
          :label="$t('hubs.addressDialog.label')"
          :value="slug"
          :error-text="fieldErrors.slug"
          :class="{ 'ion-invalid': !!fieldErrors.slug, 'ion-touched': !!fieldErrors.slug }"
          @ion-input="slug = value($event)"
        />
        <p class="address-lead">
          {{ $t('hubs.addressDialog.lead') }}
          <strong
            class="address-host"
            data-testid="address-dialog-host"
          >{{ host }}</strong>
        </p>
        <ul class="address-consequences">
          <li
            v-for="item in consequences"
            :key="item.text"
          >
            <HubIcon
              class="address-consequence-icon"
              :name="item.icon"
              aria-hidden="true"
            />
            <span>{{ item.text }}</span>
          </li>
        </ul>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.address-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.address-lead {
  margin: 0;
  font-size: 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
  overflow-wrap: anywhere;
}
.address-host {
  display: block;
  margin-top: 2px;
  color: var(--ion-text-color);
}
.address-consequences {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 0.88rem;
}
.address-consequences li {
  display: flex;
  gap: 10px;
}
.address-consequence-icon {
  flex: none;
  margin-top: 2px;
  color: color-mix(in oklab, var(--ion-text-color) 60%, transparent);
}
</style>
