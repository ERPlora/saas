// Types of `billing.promo.check` (billing/schemas/promo_codes.py), written by hand as frontend/sdk-types.d.ts.

/** `billing.PromoKind`: what a promo code grants. */
export type PromoKind = 'trial_days' | 'free_months';

/** `billing.PromoCheckIn`. */
export interface PromoCheckIn {
  code: string;
}

/** `billing.PromoCheckOut`: whether the code is valid now and what it grants (0 for the other kind, and for both
 *  when it is not valid). */
export interface PromoCheckOut {
  code: string;
  valid: boolean;
  kind: PromoKind;
  trial_days: number;
  free_months: number;
}
