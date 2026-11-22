// What the Store has on sale (the plans and the premium apps, in the person's language) and what the business it
// sells to has (`billing.store.catalog`), with what a command left of its subscription kept until it is asked again.
import { useLiveClient } from '@erplora/ui/sdk';
import { type Ref, type ShallowRef, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import type { PlanOut } from '../../frontend/sdk-types/hubs-catalog';
import type { AppSummaryOut, StoreCatalogOut, SubscriptionModuleOut, SubscriptionOut } from '../../frontend/sdk-types/store';

export function useStoreCatalog(business: Readonly<Ref<{ id: string } | null>>) {
  const { locale } = useI18n();
  const client = useLiveClient();
  const plans = shallowRef<PlanOut[] | null>(null);
  const apps = shallowRef<AppSummaryOut[] | null>(null);
  const catalog = shallowRef<StoreCatalogOut | null>(null);
  const failed = shallowRef(false);
  let catalogToken = 0;

  async function loadOnSale(): Promise<void> {
    try {
      const [planList, appList] = await Promise.all([
        client.api.call('hubs.plan.list'),
        client.api.call('apps.app.list', { premium: true }),
      ]);
      plans.value = planList.plans;
      apps.value = appList.apps;
    } catch (error) {
      console.error('billing: the plans or the app catalog could not be loaded', error);
      failed.value = true;
    }
  }

  async function loadCatalog(hubId: string): Promise<void> {
    const mine = ++catalogToken;
    try {
      const answer = await client.api.call('billing.store.catalog', { hub_id: hubId });
      if (mine === catalogToken) catalog.value = answer;
    } catch (error) {
      if (mine !== catalogToken) return;
      console.error('billing: what the business has could not be loaded', error);
      failed.value = true;
    }
  }

  function retry(): void {
    failed.value = false;
    void loadOnSale();
    if (business.value) void loadCatalog(business.value.id);
  }

  // The catalog speaks the person's language: asked again when it changes.
  watch(locale, () => void loadOnSale(), { immediate: true });
  watch(
    () => business.value?.id,
    (id) => {
      if (id) void loadCatalog(id);
    },
    { immediate: true },
  );

  const apply = (out: SubscriptionOut) => keepSubscription(catalog, out);
  return { plans, apps, catalog, failed, loadCatalog, retry, apply };
}

/** What a command left of the subscription, kept here until the catalog is asked again. */
function keepSubscription(catalog: ShallowRef<StoreCatalogOut | null>, out: SubscriptionOut): void {
  const now = catalog.value;
  if (!now || now.hub_id !== out.hub_id) return;
  const items = new Map<string, SubscriptionModuleOut>(out.modules.map((item) => [item.slug, item]));
  const nowTime = Date.now();
  catalog.value = {
    ...now,
    subscription: {
      plan: out.plan,
      billing_interval: out.billing_interval,
      status: out.status,
      paying: true,
      cancel_at_period_end: out.cancel_at_period_end,
      current_period_end: out.current_period_end,
      trial_plan: now.subscription?.trial_plan ?? null,
      trial_end: out.trial_end,
      scheduled_change: out.scheduled_change ?? null,
    },
    modules: now.modules.map((module) => {
      const item = items.get(module.slug);
      const live = !!item && (!item.valid_until || Date.parse(item.valid_until) > nowTime);
      return {
        ...module,
        owned: live,
        source: live ? (item.source as 'plan' | 'purchase') : null,
        valid_until: live ? item.valid_until : null,
      };
    }),
  };
}
