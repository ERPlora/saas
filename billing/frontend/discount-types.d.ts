// Types of a discount as the panel reads it (billing/schemas/discounts.py), written by hand as frontend/sdk-types.d.ts.
import type { BillingInterval } from '../../frontend/sdk-types';

/** `billing.DiscountDuration`: once, for some months or forever. */
export type DiscountDuration = 'once' | 'repeating' | 'forever';

/** `billing.DiscountAppliesTo`: what a discount applies to. */
export type DiscountAppliesTo = 'plans';

/** `billing.DiscountAppliesToOut`: the plans it names (none = every plan) and the billings it goes with. */
export interface DiscountAppliesToOut {
  kind: DiscountAppliesTo;
  plans: string[];
  intervals: BillingInterval[];
}

/** `billing.DiscountOut`: a percentage or an amount in cents (the other `null`), once, for some months or forever. */
export interface DiscountOut {
  percent_off: number | null;
  amount_off_cents: number | null;
  currency: string;
  duration: DiscountDuration;
  duration_in_months: number | null;
  applies_to: DiscountAppliesToOut;
}

/** `billing.SubscriptionDiscountOut`: the discount a subscription carries, its code and when it ends (`null`: never). */
export interface SubscriptionDiscountOut {
  code: string;
  ends_at: string | null;
  terms: DiscountOut;
}
