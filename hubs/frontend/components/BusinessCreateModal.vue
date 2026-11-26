<script setup lang="ts">
// «Create business», the dialog of the businesses page: the form, then the
// preparation, then «ready» or why not. With the account's Free business filling its quota, the dialog says so
// instead of the form, naming it, and offers to change its plan. The page holds what it shows: whether it is open,
// the business it follows (`created`) and that business as its own `hubs.business.get` says it is now
// (`createdNow`); the dialog hands back a business its form created (`created`) and the one to open (`open`).
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { HubIcon, WebOnly } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, nextTick, shallowRef, toRef, useTemplateRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { STORE } from '../../../accounts/frontend/paths';
import type { BusinessDetailOut, HubRefOut } from '../../../frontend/sdk-types/hubs';
import { preparationFailed, preparingLeadKey } from '../business-status';
import BusinessCreateForm from './BusinessCreateForm.vue';
import BusinessPreparing from './BusinessPreparing.vue';

const props = defineProps<{
  /** The business just created, followed until it is ready; `null` shows the form. */
  created: { id: string; name: string; host: string; typeName: string | null } | null;
  /** That business as `hubs.business.get` says it is now; `undefined` until it answers. */
  createdNow: BusinessDetailOut | undefined;
  /** The account's Free business when its Free ones fill the quota: a new business would be Free, so
   *  the dialog says so instead of a form that would be refused. */
  freeBusiness: HubRefOut | null;
  /** The business the page is opening (its id): «Open business» waits for it. */
  opening: string | null;
}>();
const createOpen = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{
  created: [business: { id: string; name: string; host: string }, extra: { typeName: string | null }];
  open: [business: BusinessDetailOut];
}>();

const { t } = useI18n();
const router = useRouter();
const created = toRef(() => props.created);
const createdNow = toRef(() => props.createdNow);
const freeBusiness = toRef(() => props.freeBusiness);

const creating = shallowRef(false);
const createForm = useTemplateRef<InstanceType<typeof BusinessCreateForm>>('createForm');
/** The sentence over its preparation: none during a platform pause (`BusinessPreparing` says the pause). */
const preparingLead = computed(() => preparingLeadKey(createdNow.value?.maintenance));

const limited = computed(() => !created.value && !!freeBusiness.value);

function changeFreePlan(id: string): void {
  createOpen.value = false;
  void router.push(`${STORE}/plans?business=${id}`);
}

const phase = computed<'form' | 'preparing' | 'ready' | 'error'>(() => {
  if (!created.value) return 'form';
  const now = createdNow.value;
  if (now && preparationFailed(now)) return 'error';
  return now?.can.open ? 'ready' : 'preparing';
});

// Each step puts the focus on its own button: a screen reader hears where it is.
const listButton = useTemplateRef<{ $el: HTMLElement }>('listButton');
const openButton = useTemplateRef<{ $el: HTMLElement }>('openButton');
watch(phase, async (now) => {
  if (now === 'form') return;
  await nextTick();
  (now === 'ready' ? openButton.value : listButton.value)?.$el.focus();
});
const createTitle = computed(() => {
  const name = created.value?.name ?? '';
  return {
    form: t('hubs.createModal.title'),
    preparing: t('hubs.createModal.preparingTitle', { name }),
    ready: t('hubs.createModal.readyTitle'),
    error: t('hubs.createModal.errorTitle'),
  }[phase.value];
});

function closeCreate(): void {
  createOpen.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="createOpen"
    testid="create-modal"
    :title="createTitle"
    :submit-label="$t('hubs.create.submit')"
    submit-icon="ion:add-outline"
    :pending="creating"
    @submit="createForm?.submit()"
  >
    <InlineFeedback
      v-if="limited && freeBusiness"
      tone="info"
      icon="ion:storefront-outline"
      data-testid="create-free-limit"
      :heading="$t('hubs.create.freeLimit.heading')"
    >
      {{ $t('hubs.create.freeLimit.body', { name: freeBusiness.name }) }}
      <WebOnly>
        <template #app>
          <p class="create-foot">
            {{ $t('hubs.common.storeInBrowser') }}
          </p>
        </template>
      </WebOnly>
    </InlineFeedback>
    <template v-else-if="phase === 'form'">
      <h2 class="create-heading">
        {{ $t('hubs.create.heading') }}
      </h2>
      <p class="create-lead">
        {{ $t('hubs.create.lead') }}
      </p>
      <BusinessCreateForm
        ref="createForm"
        :submit-button="false"
        @update:pending="creating = $event"
        @created="(business, extra) => emit('created', business, extra)"
      />
      <p class="create-foot">
        {{ $t('hubs.create.foot') }}
      </p>
    </template>
    <template v-else-if="phase === 'preparing' && created">
      <p
        v-if="preparingLead"
        class="create-lead"
      >
        {{ $t(preparingLead) }}
      </p>
      <BusinessPreparing
        :id="created.id"
        :name="created.name"
        :type-name="created.typeName"
        :maintenance="createdNow?.maintenance ?? null"
        last="ready"
      />
      <p class="create-foot">
        {{ $t('hubs.createModal.closeHint') }}
      </p>
    </template>
    <div
      v-else-if="phase === 'ready' && created"
      class="ion-text-center"
    >
      <div class="result-icon is-success">
        <HubIcon
          name="ion:checkmark-outline"
          aria-hidden="true"
        />
      </div>
      <p class="create-lead">
        <i18n-t keypath="hubs.createModal.readyAddress">
          <template #host>
            <span class="mono">{{ createdNow?.host ?? created.host }}</span>
          </template>
        </i18n-t>
      </p>
    </div>
    <div
      v-else-if="created"
      class="ion-text-center"
    >
      <div class="result-icon is-danger">
        <HubIcon
          name="ion:warning-outline"
          aria-hidden="true"
        />
      </div>
      <p class="create-lead">
        {{ $t('hubs.createModal.error', { name: created.name }) }}
      </p>
    </div>

    <template
      v-if="limited && freeBusiness"
      #footer
    >
      <WebOnly>
        <ion-button
          data-testid="create-free-limit-store"
          @click="changeFreePlan(freeBusiness.id)"
        >
          <HubIcon
            slot="start"
            name="lucide:layers"
            aria-hidden="true"
          />
          {{ $t('hubs.create.freeLimit.store', { name: freeBusiness.name }) }}
        </ion-button>
      </WebOnly>
    </template>
    <template
      v-else-if="phase !== 'form'"
      #footer
    >
      <ion-button
        ref="listButton"
        data-testid="create-modal-close-list"
        :fill="phase === 'ready' ? 'clear' : 'solid'"
        @click="closeCreate"
      >
        <HubIcon
          slot="start"
          name="ion:storefront-outline"
          aria-hidden="true"
        />
        {{ $t('hubs.createModal.goToList') }}
      </ion-button>
      <ion-button
        v-if="phase === 'ready' && createdNow"
        ref="openButton"
        class="icon-action"
        data-testid="create-modal-open"
        :disabled="!!opening"
        :aria-label="$t('hubs.common.openBusiness')"
        :title="$t('hubs.common.openBusiness')"
        @click="emit('open', createdNow)"
      >
        <HubIcon
          slot="icon-only"
          name="ion:log-in-outline"
          aria-hidden="true"
        />
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
.mono {
  font-family: var(--font-mono, ui-monospace, monospace);
}
.create-heading {
  margin: 0 0 4px;
  font-size: 1.05rem;
  font-weight: 600;
}
.create-lead {
  margin: 0 0 16px;
  font-size: 0.9rem;
  line-height: 1.5;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.create-foot {
  margin: 14px 0 0;
  font-size: 0.85rem;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.result-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin: 8px auto 12px;
  border-radius: 999px;
  font-size: 30px;
}
.result-icon.is-success {
  color: var(--ion-color-success);
  background: color-mix(in srgb, var(--ion-color-success) 14%, transparent);
}
.result-icon.is-danger {
  color: var(--ion-color-danger);
  background: color-mix(in srgb, var(--ion-color-danger) 14%, transparent);
}
</style>
