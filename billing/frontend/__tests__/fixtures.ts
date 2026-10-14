// Data of the Store's tests, shaped as the server answers it: the account's businesses
// (`hubs.business.list`), the plans on sale (`hubs.plan.list`), the app catalog (`apps.app.list`) and what
// billing sells each business (`billing.store.catalog`).
import type {
  AppSummaryOut,
  BusinessRowOut,
  PlanOut,
  StoreCatalogOut,
  StoreModuleOut,
  StoreSubscriptionOut,
} from '../../../frontend/sdk-types';

export function businessRow(id: string, name: string, extra: Partial<BusinessRowOut> = {}): BusinessRowOut {
  return {
    id,
    slug: id,
    name,
    host: `${id}.localhost:8000`,
    status: 'active',
    status_label: 'Active',
    plan: { slug: 'starter', name: 'Starter' },
    role: 'hub_owner',
    role_label: 'Owner',
    last_opened_at: null,
    can_open: true,
    open_blocked_reason: null,
    hub_error: null,
    deletion_requested_at: null,
    purge_after: null,
    created_at: '2026-03-02T10:00:00Z',
    can: { open: true, manage: true, restore: false, delete: true },
    unpaid_reason: null,
    unpaid_since: null,
    pay_url: null,
    is_payer: true,
    ...extra,
  };
}

export const BAKERY = businessRow('bakery', 'Panadería López');
export const CAFE = businessRow('cafe', 'Café Central', { plan: { slug: 'free', name: 'Free' } });
export const PLAZA = businessRow('plaza', 'Bar La Plaza', {
  status: 'past_due',
  status_label: 'Payment pending',
  unpaid_reason: 'card_declined',
  unpaid_since: '2026-10-10T08:00:00Z',
  pay_url: 'https://invoice.stripe.com/i/plaza',
});
export const SALON = businessRow('salon', 'Peluquería Ana', { role: 'hub_manager', role_label: 'Manager' });

export function businessPage(rows: BusinessRowOut[]) {
  return { rows, total: rows.length, limit: 100, offset: 0, invitations: [], ownership_offers: [] };
}

export function plan(slug: string, name: string, monthly: string, annual: string, extra: Partial<PlanOut> = {}): PlanOut {
  return {
    slug,
    name,
    description: `${name} description`,
    price_monthly: monthly,
    price_annual: annual,
    features: [`${name} feature`],
    featured_label: '',
    max_users: 0,
    max_devices: 0,
    trial_period_days: 0,
    has_trial: false,
    support_level_label: 'Email',
    included_level_label: 'Basic',
    upgrade_only: false,
    internal_only: false,
    ...extra,
  };
}

export const FREE = plan('free', 'Free', '0.00', '0.00', { max_users: 3, max_devices: 1 });
export const STARTER = plan('starter', 'Starter', '29.99', '299.90');
export const PLANS = { signup_trial_days: 15, cheapest_slug: 'free', plans: [FREE, STARTER] };

export function app(id: string, name: string, extra: Partial<AppSummaryOut> = {}): AppSummaryOut {
  return {
    id,
    name,
    summary: `${name} summary`,
    icon_svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path d="M0 0h512v512H0z"/></svg>`,
    category: 'sales',
    premium: true,
    verticals: [],
    ...extra,
  };
}

export const APPS = {
  apps: [
    app('booking', 'Bookings', { summary: 'Calendar, online bookings and reminders.' }),
    app('loyalty', 'Loyalty', { summary: 'Points, cards and discounts for customers.' }),
    app('sales', 'Sales', { premium: false }),
  ],
};

export function storeModule(slug: string, monthly: number, extra: Partial<StoreModuleOut> = {}): StoreModuleOut {
  return {
    slug,
    tier: 'basic',
    price_monthly_cents: monthly,
    price_annual_cents: monthly * 10,
    owned: false,
    source: null,
    valid_until: null,
    ...extra,
  };
}

export function subscription(extra: Partial<StoreSubscriptionOut> = {}): StoreSubscriptionOut {
  return {
    plan: 'starter',
    billing_interval: 'month',
    status: 'active',
    paying: true,
    cancel_at_period_end: false,
    current_period_end: '2026-10-31T12:00:00Z',
    trial_plan: null,
    trial_end: null,
    ...extra,
  };
}

export const FREE_SUBSCRIPTION = subscription({
  plan: 'free',
  paying: false,
  current_period_end: null,
  trial_plan: 'starter',
  trial_end: '2099-10-20T12:00:00Z',
});

export function catalog(hubId: string, extra: Partial<StoreCatalogOut> = {}): StoreCatalogOut {
  return {
    hub_id: hubId,
    subscription: subscription(),
    modules: [storeModule('booking', 900), storeModule('loyalty', 600)],
    ...extra,
  };
}
