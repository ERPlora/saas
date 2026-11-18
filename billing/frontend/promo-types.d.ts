// Types of `billing.promo.check` (billing/schemas/promo_codes.py), written by hand as frontend/sdk-types/.
import type { DiscountOut } from './discount-types';

/** `billing.PromoCheckIn`. */
export interface PromoCheckIn {
  code: string;
}

/** `billing.PromoCheckOut`: whether the code is valid now and what it grants: trial days (0 without them) or a
 *  discount (`null` without one, and both when it is not valid). */
export interface PromoCheckOut {
  code: string;
  valid: boolean;
  trial_days: number;
  discount: DiscountOut | null;
}
