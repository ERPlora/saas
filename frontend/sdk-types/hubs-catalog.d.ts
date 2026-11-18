// hubs (hubs/schemas/): the business types and the plans on sale.

/** `hubs.BusinessTypeListIn`. */
export interface BusinessTypeListIn {
  sector?: string;
}

/** `hubs.SectorRefOut`. */
export interface SectorRefOut {
  code: string;
  name: string;
}

/** `hubs.BusinessTypeOut`: a business type in the caller's language. */
export interface BusinessTypeOut {
  code: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  sector: SectorRefOut | null;
  vertical: string;
  updated_at: string;
}

/** `hubs.BusinessTypeListOut`. */
export interface BusinessTypeListOut {
  business_types: BusinessTypeOut[];
}

/** `hubs.PlanOut`: a plan on sale; prices net (VAT excluded), in euros, as decimal strings. */
export interface PlanOut {
  slug: string;
  name: string;
  description: string;
  price_monthly: string;
  price_annual: string;
  features: string[];
  featured_label: string;
  /** 0 = unlimited. */
  max_users: number;
  /** 0 = unlimited. */
  max_devices: number;
  trial_period_days: number;
  has_trial: boolean;
  support_level_label: string;
  included_level_label: string;
  /** How much room the plan has, relative to the full tier («Basic, for one device», «Double»…). */
  resources_label: string;
  /** Requests to the AI assistant the plan includes each month (one request = one message); 0 = none. */
  assistant_messages_per_month: number;
  /** WhatsApp messages the plan includes each month; 0 = none. */
  whatsapp_messages_per_month: number;
  /** Apps the business may choose to turn on at once, the ones they require aside; 0 = no limit. */
  max_apps: number;
  /** Whether the business's public website may go on a domain of its own (HUBS-F17); never the app. */
  includes_custom_domain: boolean;
  upgrade_only: boolean;
  internal_only: boolean;
}

/** `hubs.PlanListOut`. */
export interface PlanListOut {
  signup_trial_days: number;
  cheapest_slug: string | null;
  plans: PlanOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'hubs.business_type.list': { input: BusinessTypeListIn | undefined; output: BusinessTypeListOut };
    'hubs.plan.list': { input: Record<string, never> | undefined; output: PlanListOut };
  }
}
