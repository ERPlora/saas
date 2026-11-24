// The Billing section (billing/schemas/): the subscriptions and the payment details.
import type { SubscriptionDiscountOut } from '../../billing/frontend/discount-types';

import type { InvoiceBusinessOut } from './billing-invoices';
import type { BillingInterval, ScheduledChangeOut } from './store';

/** `billing.VatStatus`: the verdict a VAT number gets. */
export type VatStatus = 'verified' | 'invalid' | 'unavailable' | 'national' | 'outside_vies';

/** The actions of a subscription row (`billing.SubscriptionRowOut.actions`), the fixed one first. */
export type SubscriptionAction = 'take_over' | 'change_plan' | 'keep_plan' | 'view_invoice' | 'cancel_plan' | 'view_invoices';

/** `billing.SubscriptionListIn`. */
export interface SubscriptionListIn {
  limit?: number;
  offset?: number;
  /** One business's subscription; only among the account's. */
  hub_id?: string | null;
  status?: 'active' | 'trialing' | 'past_due' | 'unpaid' | 'incomplete' | 'paused' | null;
}

/** `billing.SubscriptionPlanOut`: the plan, at its net price. */
export interface SubscriptionPlanOut {
  slug: string;
  name: string;
  interval: BillingInterval;
  price_cents: number;
}

/** `billing.SubscriptionModuleRowOut`: a paid module of the business (`price_cents` null off sale). */
export interface SubscriptionModuleRowOut {
  slug: string;
  interval: BillingInterval;
  price_cents: number | null;
  source: 'plan' | 'purchase';
  /** Cancelled: it works until then. */
  valid_until: string | null;
}

/** `billing.NextInvoiceOut`: with VAT (`total_cents` null while the payer's place is unknown). */
export interface NextInvoiceOut {
  date: string | null;
  total_cents: number | null;
  currency: string;
}

/** `billing.SubscriptionCanOut`. */
export interface SubscriptionCanOut {
  /** «Keep it with my card»: the business was handed over and its plan is still on the previous payer's card. */
  take_over: boolean;
  change_plan: boolean;
  cancel_plan: boolean;
  keep_plan: boolean;
  view_invoice: boolean;
  view_invoices: boolean;
}

/** `billing.SubscriptionRowOut`: one business Stripe bills. */
export interface SubscriptionRowOut {
  business: InvoiceBusinessOut;
  plan: SubscriptionPlanOut;
  modules: SubscriptionModuleRowOut[];
  /** `null` while the plan ends at the end of the period, or once the business was deleted. */
  next_invoice: NextInvoiceOut | null;
  /** Stripe's status of the subscription; `deleting` once the business was deleted, as its own page says. */
  status: string;
  status_label: string;
  cancelling: boolean;
  ends_at: string | null;
  cancel_requested: boolean;
  unpaid_invoice_id: string | null;
  /** A downgrade waiting for the end of the period. */
  scheduled_change: ScheduledChangeOut | null;
  /** The plan is charged to the card of another account (the payer before a hand-over, HUBS-F28). */
  paid_by_another_account: boolean;
  /** The discount of a promo code it carries while it applies to the renewal. */
  discount: SubscriptionDiscountOut | null;
  actions: SubscriptionAction[];
  can: SubscriptionCanOut;
}

/** `billing.SubscriptionListOut`. */
export interface SubscriptionListOut {
  rows: SubscriptionRowOut[];
  total: number;
  limit: number;
  offset: number;
}

/** `billing.PaymentMethodIn`. */
export interface PaymentMethodIn {
  hub_id?: string | null;
}

/** `billing.CardOut`. */
export interface CardOut {
  brand: string;
  last4: string;
  exp_month: number;
  exp_year: number;
}

/** `billing.LastFailureOut`. */
export interface LastFailureOut {
  at: string;
  business: string;
}

/** `billing.PaymentMethodRowOut`: the card of one payer and the businesses it pays. */
export interface PaymentMethodRowOut {
  businesses: InvoiceBusinessOut[];
  card: CardOut | null;
  unavailable: boolean;
  last_failure: LastFailureOut | null;
}

/** `billing.PaymentMethodOut`. */
export interface PaymentMethodOut {
  methods: PaymentMethodRowOut[];
}

/** `billing.PortalOpenIn`. */
export interface PortalOpenIn {
  hub_id: string;
}

/** `billing.PortalOpenOut`: Stripe's Customer Portal, one use. */
export interface PortalOpenOut {
  url: string;
}

/** `billing.VatCheckIn`: a VAT number, read in `country` when typed without its prefix. */
export interface VatCheckIn {
  vat_number: string;
  country?: string;
}

/** `billing.VatCheckOut`: the verdict that will price a sale to this number. */
export interface VatCheckOut {
  vat_number: string;
  status: VatStatus;
  valid: boolean | null;
  name: string;
  address: string;
  consultation_number: string;
  checked_at: string | null;
  is_current: boolean;
  reverse_charge: boolean;
  manual_override: boolean;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'billing.subscription.list': { input: SubscriptionListIn | undefined; output: SubscriptionListOut };
    'billing.payment_method.get': { input: PaymentMethodIn | undefined; output: PaymentMethodOut };
    'billing.portal.open': { input: PortalOpenIn; output: PortalOpenOut };
    'billing.vat_check.run': { input: VatCheckIn; output: VatCheckOut };
  }
}
