// Test helper of a plan's card in the Store (PlanCard.vue): mounts it with the props the Store hands it, and finds
// its parts by test id.
import type { BillingInterval } from '../../../frontend/sdk-types/store';
import PlanCard from '../components/PlanCard.vue';
import type { Block } from '../store';
import { STARTER, subscription } from './fixtures';
import { mountBilling } from './mount-billing';

/** The billings Stripe sells a plan with, as the admin pastes its prices: the annual one only with an annual price. */
export function soldAsPasted(plan: typeof STARTER): BillingInterval[] {
  return Number(plan.price_annual) > 0 ? ['month', 'year'] : ['month'];
}

export async function card(props: {
  plan?: typeof STARTER;
  period?: BillingInterval;
  sold?: BillingInterval[];
  subscription?: unknown;
  block?: Block | null;
  scheduledPlanName?: string;
  locale?: 'en' | 'es';
}) {
  const { locale, ...rest } = props;
  const plan = rest.plan ?? STARTER;
  const m = await mountBilling(PlanCard, {
    locale,
    props: { plan, period: 'month', sold: soldAsPasted(plan), subscription: subscription(), block: null, ...rest },
  });
  const text = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, text };
}
