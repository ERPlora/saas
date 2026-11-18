// The Store: billing (billing/schemas/), the app catalog (apps/schemas.py) and the payer of a business
// (hubs/schemas/ `BillingProfile*`).
import type { PromoCheckIn, PromoCheckOut } from '../../billing/frontend/promo-types';

import type { PlanOut } from './hubs-catalog';

/** `billing.Interval`: how a subscription is billed. */
export type BillingInterval = 'month' | 'year';

/** `billing.ScheduledChangeOut`: a plan change that starts with the next period (a downgrade). */
export interface ScheduledChangeOut {
  plan: string;
  interval: BillingInterval;
  starts_at: string;
}

/** `billing.CheckoutStartIn`: a plan (with its billing) OR a module, one at a time. */
export interface CheckoutStartIn {
  hub_id: string;
  plan?: string | null;
  interval?: BillingInterval;
  module?: string | null;
  promo_code?: string;
}

/** `billing.ChargePreviewOut`: what confirming charges NOW (Stripe's prorated preview), in cents. */
export interface ChargePreviewOut {
  amount_due_cents: number;
  tax_cents: number;
  currency: string;
  /** Sent back by the confirmation, so the charge is the preview's to the cent. */
  proration_date: number;
  /** During a trial nothing is charged now: when it starts (unix seconds). */
  charge_starts_at: number | null;
}

/** `billing.CheckoutStartOut`: `checkout` → Embedded Checkout with `client_secret`; `confirm` → `preview`. */
export interface CheckoutStartOut {
  flow: 'checkout' | 'confirm';
  session_id: string | null;
  client_secret: string | null;
  publishable_key: string | null;
  preview: ChargePreviewOut | null;
}

/** `billing.CheckoutConfirmIn`: a module added at the previewed proration. */
export interface CheckoutConfirmIn {
  hub_id: string;
  module: string;
  proration_date: number;
}

/** `billing.PlanChangeIn`: another plan or billing, at the previewed proration. */
export interface PlanChangeIn {
  hub_id: string;
  plan: string;
  interval?: BillingInterval;
  proration_date: number;
  promo_code?: string;
}

/** `billing.HubIn`. */
export interface HubIn {
  hub_id: string;
}

/** `billing.ModuleIn`. */
export interface ModuleIn {
  hub_id: string;
  module: string;
}

/** `billing.SubscriptionModuleOut`. */
export interface SubscriptionModuleOut {
  slug: string;
  /** `plan` (included in it) or `purchase`. */
  source: string;
  valid_until: string | null;
}

/** `billing.SubscriptionOut`: the subscription of a business after a change, as Stripe left it. */
export interface SubscriptionOut {
  hub_id: string;
  plan: string;
  billing_interval: BillingInterval;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  trial_end: string | null;
  modules: SubscriptionModuleOut[];
  /** A downgrade waiting for the end of the period («Starter from 1 Nov»). */
  scheduled_change: ScheduledChangeOut | null;
}

/** `billing.StoreCatalogIn`. */
export interface StoreCatalogIn {
  hub_id: string;
}

/** `billing.StoreModuleOut`: a paid module on sale and what the business has of it (prices net, cents). */
export interface StoreModuleOut {
  slug: string;
  tier: string;
  price_monthly_cents: number;
  /** 0 = no annual option. */
  price_annual_cents: number;
  owned: boolean;
  source: 'plan' | 'purchase' | null;
  valid_until: string | null;
  /** Sold to new buyers; off sale it is only listed to the business that still has it. */
  on_sale: boolean;
  /** The catalog's name, summary and icon of its app (listed or retired); the slug without its app. */
  name: string;
  summary: string;
  icon_svg: string;
}

/** `billing.StoreSubscriptionOut`: the business's plan as the Store needs it. */
export interface StoreSubscriptionOut {
  plan: string;
  billing_interval: BillingInterval;
  status: string;
  /** Stripe bills it already: changes are confirmed with their proration; otherwise the checkout. */
  paying: boolean;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  trial_plan: string | null;
  trial_end: string | null;
  /** A downgrade waiting for the end of the period: the card of the current plan offers to keep it. */
  scheduled_change: ScheduledChangeOut | null;
}

/** `billing.StoreCatalogOut`. */
export interface StoreCatalogOut {
  hub_id: string;
  subscription: StoreSubscriptionOut | null;
  modules: StoreModuleOut[];
  /** The paid plans the business may move to: no upgrade-only plan while Stripe does not bill it; the internal ones
   *  only to a business ERPlora's staff marked. */
  offered_plans: string[];
  /** The internal plans the business is offered, and the one it has: `hubs.plan.list` lists only the public ones. */
  internal_plans: PlanOut[];
}

/** `apps.AppListIn`: every filter optional and lenient. */
export interface AppListIn {
  q?: string | null;
  category?: string | null;
  premium?: boolean | null;
  vertical?: string | null;
}

/** `apps.AppSummaryOut`: a card of the catalog, in the caller's language; `icon_svg` already cleaned. */
export interface AppSummaryOut {
  id: string;
  name: string;
  summary: string;
  icon_svg: string;
  category: string | null;
  premium: boolean;
  verticals: string[];
}

/** `apps.AppListOut`. */
export interface AppListOut {
  apps: AppSummaryOut[];
}

/** `apps.AppByIdIn`. */
export interface AppByIdIn {
  id: string;
}

/** `apps.RequiredAppOut`. */
export interface RequiredAppOut {
  id: string;
  name: string;
  listed: boolean;
}

/** `apps.AppOut`: a listed app's page. */
export interface AppOut extends AppSummaryOut {
  description: string;
  requires: RequiredAppOut[];
  has_docs: boolean;
}

/** `hubs.BillingProfileGetIn`. */
export interface BillingProfileGetIn {
  hub_id: string;
}

/** `hubs.BillingProfileIn`: who ERPlora invoices for the business (`''` = not given). */
export interface BillingProfileIn {
  hub_id: string;
  billing_name?: string;
  tax_id?: string;
  billing_address?: string;
  billing_city?: string;
  billing_postal_code?: string;
  billing_country?: string;
  billing_email?: string;
  same_as_business?: boolean;
}

/** `hubs.BillingProfileOut`: empty while another account pays (`paid_by_another_account`). */
export interface BillingProfileOut {
  hub_id: string;
  paid_by_another_account: boolean;
  billing_name: string;
  tax_id: string;
  billing_address: string;
  billing_city: string;
  billing_postal_code: string;
  billing_country: string;
  billing_email: string;
  same_as_business: boolean;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'apps.app.list': { input: AppListIn | undefined; output: AppListOut };
    'apps.app.get': { input: AppByIdIn; output: AppOut };
    'hubs.billing_profile.get': { input: BillingProfileGetIn; output: BillingProfileOut };
    'hubs.billing_profile.update': { input: BillingProfileIn; output: BillingProfileOut };
    'billing.store.catalog': { input: StoreCatalogIn; output: StoreCatalogOut };
    'billing.promo.check': { input: PromoCheckIn; output: PromoCheckOut };
    'billing.checkout.start': { input: CheckoutStartIn; output: CheckoutStartOut };
    'billing.checkout.confirm': { input: CheckoutConfirmIn; output: SubscriptionOut };
    'billing.plan.change': { input: PlanChangeIn; output: SubscriptionOut };
    'billing.plan.cancel': { input: HubIn; output: SubscriptionOut };
    'billing.plan.keep': { input: HubIn; output: SubscriptionOut };
    'billing.plan.take_over': { input: HubIn; output: CheckoutStartOut };
    'billing.module.cancel': { input: ModuleIn; output: SubscriptionOut };
    'billing.module.keep': { input: ModuleIn; output: SubscriptionOut };
  }
}
