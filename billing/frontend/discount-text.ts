// What the panel says of a discount, derived from its terms (billing.promo.check, a subscription's discount): what
// it takes off, for how long, when the plan's price starts and until when a subscription carries it.
import type { BillingInterval } from '../../frontend/sdk-types/store';
import type { DiscountOut, SubscriptionDiscountOut } from './discount-types';

/** The translator of the panel and how it says an amount in cents. */
export interface Speak {
  t: (key: string, named?: Record<string, unknown>, plural?: number) => string;
  money: (cents: number) => string;
}

/** What a plan costs before the discount, per period. */
export interface PlanPrice {
  cents: number;
  interval: BillingInterval;
}

function offText({ t, money }: Speak, discount: DiscountOut): string {
  if (discount.percent_off === 100) return t('billing.discount.off.free');
  if (discount.percent_off !== null) return t('billing.discount.off.percent', { percent: discount.percent_off });
  return t('billing.discount.off.amount', { amount: money(discount.amount_off_cents ?? 0) });
}

/** «Free for 6 months», «20% off on the first payment», «€10.00 off forever». */
export function discountText(speak: Speak, discount: DiscountOut): string {
  const off = offText(speak, discount);
  if (discount.duration === 'repeating') {
    const months = discount.duration_in_months ?? 1;
    return speak.t('billing.discount.duration.repeating', { off, months }, months);
  }
  return speak.t(`billing.discount.duration.${discount.duration}`, { off });
}

/** Whether the first payment of `price` is all discounted (nothing is charged on the card today). */
function firstPaymentFree(discount: DiscountOut, price: PlanPrice): boolean {
  return discount.percent_off === 100 || (discount.amount_off_cents ?? 0) >= price.cents;
}

/** The checkout's notice: the discount, when the plan's regular price starts, and whether today's charge is 0. */
export function checkoutNotice(speak: Speak, discount: DiscountOut, price: PlanPrice): string {
  const said = discountText(speak, discount);
  const then =
    discount.duration === 'forever'
      ? speak.t('billing.checkout.discountOnly', { discount: said })
      : speak.t(price.interval === 'year' ? 'billing.checkout.discountThenYear' : 'billing.checkout.discountThenMonth', {
          discount: said,
          price: speak.money(price.cents),
        });
  return firstPaymentFree(discount, price) ? `${then} ${speak.t('billing.checkout.nothingDueToday')}` : then;
}

/** What a subscription carries: «Free until May 16, 2027», or «€10.00 off forever». */
export function carriedText(speak: Speak, carried: SubscriptionDiscountOut, day: (iso: string) => string): string {
  if (carried.ends_at === null) return discountText(speak, carried.terms);
  return speak.t('billing.subscriptions.discountUntil', { off: offText(speak, carried.terms), date: day(carried.ends_at) });
}
