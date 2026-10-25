<script setup lang="ts">
// The Store (`/dashboard/store/:tab`, round 17 §2.10; mockups `store.html`): the shell's page, with its two sections
// in the footer tabbar, Plans · Modules, each at its own address and carrying the business it sells to
// (`?business=`, which the shop writes back when the owner picks another).
// It sells, so it is the web's only (PLAN-SAAS §3.6 point 6; README §4): inside the apps and on the
// account surface — a deep link too — it says «The store is not in the app» and how to buy from a
// browser (on the account surface, already a browser, why nothing is bought there: audit 2 S-09), WITHOUT a link out (what Google Play admits of a consumption-only app), and nothing of the
// shop loads: no prices, no Stripe. `<WebOnly>` follows the surface live (a late Tauri bridge).
import { EmptyState } from '@erplora/ui/components';
import { AppPage, type ShellTab, useSurface, WebOnly } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import { BUSINESSES, STORE } from '../../../accounts/frontend/paths';
import StoreShop from '../components/StoreShop.vue';

type Tab = 'plans' | 'modules';

const props = defineProps<{
  /** The section on screen. */
  tab: Tab;
}>();

const SECTIONS: Array<{ id: Tab; icon: string }> = [
  { id: 'plans', icon: 'ion:layers-outline' },
  { id: 'modules', icon: 'ion:apps-outline' },
];

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { surface } = useSurface();

const businessId = computed(() => (typeof route.query.business === 'string' && route.query.business ? route.query.business : undefined));
const current = shallowRef<string>(props.tab);
watch(
  () => props.tab,
  (tab) => {
    current.value = tab;
  },
);

const tabs = computed<ShellTab[]>(() => {
  const query = businessId.value ? `?business=${encodeURIComponent(businessId.value)}` : '';
  return SECTIONS.map((section) => ({
    id: section.id,
    label: t(`billing.store.tabs.${section.id}`),
    icon: section.icon,
    to: `${STORE}/${section.id}${query}`,
    webOnly: true,
  }));
});

function choose(id: string): void {
  void router.replace({ path: route.path, query: { ...route.query, business: id } });
}

/** The account the app opens in the browser: already in a browser, so it says why, not where (audit 2 S-09). */
const inAccount = computed(() => surface.value === 'account');
</script>

<template>
  <AppPage
    v-model:tab="current"
    :title="$t('billing.store.title')"
    content-layout="detail"
    :tabs="tabs"
    :tabs-label="$t('billing.store.tabsLabel')"
  >
    <WebOnly>
      <StoreShop
        :tab="tab"
        :business-id="businessId"
        @update:business-id="choose"
      />
      <template #app>
        <EmptyState
          icon="globe-outline"
          :heading="inAccount ? $t('billing.store.inAccount.title') : $t('billing.store.inApp.title')"
          :message="inAccount ? $t('billing.store.inAccount.body') : $t('billing.store.inApp.body')"
          data-testid="store-in-app"
        >
          <template #action>
            <ion-button
              :router-link="BUSINESSES"
              data-testid="store-in-app-businesses"
            >
              {{ $t('billing.store.inApp.action') }}
            </ion-button>
          </template>
        </EmptyState>
      </template>
    </WebOnly>
  </AppPage>
</template>
