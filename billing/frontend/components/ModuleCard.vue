<script setup lang="ts">
// A module of the Store (mockups `store.html` «Módulos»; round 17 §2.10; UX-AUDIT-4 W-F4, X-14): the
// catalog's name, summary and icon, billing's net price at the business's billing, and the one thing the
// business can do with it. What each button does is the page's: the card emits it.
//   - «Add · €9.00/month»: one dialog per module with its own proration (or the checkout on Free).
//   - Just bought: «Activating… in <business>» (the Hub turns it on by itself) and «You have it».
//   - Owned: «You have it» (or «Included in your plan»), disabled: never on sale twice.
//   - Cancelled but still working: until when, and «Keep · no charge today».
//   - An unpaid invoice disables what charges, with the reason under the button.
import { StatusPill } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonNote } from '@ionic/vue';
import { computed, useId } from 'vue';
import { useI18n } from 'vue-i18n';

import type { BillingInterval } from '../../../frontend/sdk-types';
import { formatCents, formatDate } from '../format';
import type { Block, SaleModule } from '../store';
import AppIcon from './AppIcon.vue';

const props = defineProps<{
  module: SaleModule;
  /** The billing it is bought at: the business's. */
  interval: BillingInterval;
  block: Block | null;
  /** Bought in this visit: the Hub is turning it on. */
  activating: boolean;
  businessName: string;
  /** The business's next renewal (a kept module is charged again then). */
  renewal: string | null;
}>();

const emit = defineEmits<{ add: []; keep: [] }>();

const { t, locale } = useI18n();
const hintId = `module-hint-${useId()}`;

const cents = computed(() => (props.interval === 'year' ? props.module.priceAnnualCents : props.module.priceMonthlyCents));
const price = computed(() => formatCents(cents.value, locale.value));
const cancelled = computed(() => props.module.owned && !!props.module.validUntil && !props.activating);
const owned = computed(() => props.module.owned || props.activating);

/** Why «Add» or «Keep» does not work now. */
const hint = computed(() => {
  if (props.block) return t('billing.plans.payFirst');
  if (!owned.value && !cents.value) return t('billing.modules.monthlyOnly');
  return '';
});

const cancelledText = computed(() => {
  const date = formatDate(props.module.validUntil, locale.value);
  return props.renewal
    ? t('billing.modules.cancelled', { date, renewal: formatDate(props.renewal, locale.value) })
    : t('billing.modules.cancelledNoRenewal', { date });
});

function add(): void {
  if (!hint.value) emit('add');
}

function keep(): void {
  if (!props.block) emit('keep');
}
</script>

<template>
  <ion-card
    class="module-card"
    :data-testid="`module-${module.slug}`"
  >
    <ion-card-content class="ion-padding module-card__content">
      <div class="module-card__head">
        <span class="tile-icon"><AppIcon :svg="module.iconSvg" /></span>
        <div class="module-card__text">
          <h2
            class="card-title"
            data-testid="module-name"
          >
            {{ module.name }}
          </h2>
          <p class="card-text">
            {{ module.summary }}
          </p>
        </div>
      </div>
      <span
        class="module-card__price"
        data-testid="module-price"
      >{{ interval === 'year' ? $t('billing.modules.perYear', { price }) : $t('billing.modules.perMonth', { price }) }}</span>
      <p
        v-if="activating"
        class="module-card__state"
        data-testid="module-activating"
      >
        <StatusPill
          tone="info"
          busy
          :label="$t('billing.modules.activating')"
        />
        {{ $t('billing.modules.activatingIn', { business: businessName }) }}
      </p>
      <p
        v-else-if="cancelled"
        class="card-text module-card__note"
        data-testid="module-cancelled"
      >
        {{ cancelledText }}
      </p>
      <p
        v-else-if="module.owned && module.source === 'plan'"
        class="card-text module-card__note"
        data-testid="module-included"
      >
        {{ $t('billing.modules.included') }}
      </p>
      <div class="module-card__actions">
        <ion-button
          v-if="cancelled"
          expand="block"
          fill="outline"
          :disabled="!!block"
          :aria-describedby="block ? hintId : undefined"
          data-testid="module-keep"
          @click="keep"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
          />
          {{ $t('billing.modules.keep') }}
        </ion-button>
        <ion-button
          v-else-if="owned"
          expand="block"
          fill="outline"
          disabled
          data-testid="module-owned"
        >
          <HubIcon
            slot="start"
            name="ion:checkmark-outline"
          />
          {{ $t('billing.modules.owned') }}
        </ion-button>
        <ion-button
          v-else
          expand="block"
          fill="outline"
          :disabled="!!hint"
          :aria-describedby="hint ? hintId : undefined"
          data-testid="module-add"
          @click="add"
        >
          <HubIcon
            slot="start"
            name="ion:add-outline"
          />
          {{ interval === 'year' ? $t('billing.modules.addYear', { price }) : $t('billing.modules.add', { price }) }}
        </ion-button>
        <ion-note
          v-if="hint && (!owned || cancelled)"
          :id="hintId"
          class="module-card__hint"
          data-testid="module-hint"
        >
          {{ hint }}
        </ion-note>
      </div>
    </ion-card-content>
  </ion-card>
</template>

<style scoped>
.module-card {
  margin: 0;
  display: flex;
  flex-direction: column;
}
.module-card__content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1 1 auto;
}
.module-card__head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.module-card__text {
  min-width: 0;
}
.tile-icon {
  display: inline-grid;
  place-items: center;
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  font-size: 22px;
  color: var(--ion-color-primary);
  background: color-mix(in oklab, var(--ion-color-primary) 12%, transparent);
}
.card-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.card-text {
  margin: 2px 0 0;
  font-size: 0.88rem;
  line-height: 1.45;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.module-card__price {
  font-weight: 600;
  color: var(--ion-text-color);
}
.module-card__state {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 0.85rem;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.module-card__note {
  color: var(--ion-text-color);
}
.module-card__actions {
  margin-top: auto;
}
.module-card__actions ion-button {
  margin: 0;
}
.module-card__hint {
  display: block;
  margin: 6px 0 0;
  font-size: 0.82rem;
}
</style>
<style scoped src="../../../hubs/frontend/components/buttons.css"></style>
