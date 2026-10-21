// The Store's rules, apart from the screen (round 17 §2.9–§2.11; mockups `store.html`, README §6.18):
//   - a module is sold when the catalog lists its app as premium AND billing has it on sale
//     (`apps.Module`), joined by `slug == app.id`: name, summary and icon from `apps.app.list`, prices and
//     what the business has from `billing.store.catalog`; one taken off sale (or whose app the catalog
//     retired) is still shown to the business that has it, to cancel it (saas#2589);
//   - only the owner buys for a business, and a deleted one buys nothing;
//   - a business with an unpaid invoice buys nothing more until it pays it (the server refuses it too,
//     409 `billing.invoice_unpaid`), by business;
//   - a module follows the business's billing; a business Stripe does not bill yet buys it monthly.
import type {
  AppSummaryOut,
  BillingInterval,
  BusinessRowOut,
  PlanOut,
  StoreModuleOut,
  StoreSubscriptionOut,
} from '../../frontend/sdk-types';

/** A module the Store sells the chosen business. */
export interface SaleModule {
  slug: string;
  name: string;
  summary: string;
  /** The catalog's icon, already cleaned by the server (`apps/icons.py`); may be empty. */
  iconSvg: string;
  priceMonthlyCents: number;
  /** 0 = no annual option. */
  priceAnnualCents: number;
  owned: boolean;
  source: 'plan' | 'purchase' | null;
  /** Cancelled: it works until then. */
  validUntil: string | null;
  /** Still sold. Off sale, only the business that has it sees it, to cancel it (saas#2589). */
  onSale: boolean;
}

/** What blocks buying for a business: an unpaid invoice, and whether its card was declined or changed. */
export type Block = 'card_declined' | 'card_changed' | 'unpaid';

/**
 * The modules on sale, in the catalog's order (by section, then by name in the person's language), and then the
 * ones the business still has whose app the catalog no longer lists, with billing's own name for them
 * (saas#2589: taken off sale, they are still charged until cancelled). One off sale it does not have is not shown.
 */
export function saleModules(apps: readonly AppSummaryOut[], modules: readonly StoreModuleOut[]): SaleModule[] {
  const shown = modules.filter((module) => module.on_sale || module.owned);
  const bySlug = new Map(shown.map((module) => [module.slug, module]));
  const listed = apps.flatMap((app) => {
    const module = app.premium ? bySlug.get(app.id) : undefined;
    return module ? [toSale(module, app)] : [];
  });
  const named = new Set(listed.map((module) => module.slug));
  const unlisted = shown.filter((module) => module.owned && !named.has(module.slug)).map((module) => toSale(module, null));
  return [...listed, ...unlisted];
}

function toSale(module: StoreModuleOut, app: AppSummaryOut | null): SaleModule {
  return {
    slug: module.slug,
    name: app?.name ?? module.name,
    summary: app?.summary ?? module.summary,
    iconSvg: app?.icon_svg ?? module.icon_svg,
    priceMonthlyCents: module.price_monthly_cents,
    priceAnnualCents: module.price_annual_cents,
    owned: module.owned,
    source: module.source,
    validUntil: module.valid_until,
    onSale: module.on_sale,
  };
}

/** The businesses the account may buy for: it owns them and they are not deleted. */
export function ownedBusinesses(rows: readonly BusinessRowOut[]): BusinessRowOut[] {
  return rows.filter((row) => row.role === 'hub_owner' && row.status !== 'deleting');
}

/** Why the business cannot buy now, or `null`. */
export function blockOf(row: Pick<BusinessRowOut, 'status' | 'unpaid_reason'>): Block | null {
  if (row.unpaid_reason === 'card_declined' || row.unpaid_reason === 'card_changed') return row.unpaid_reason;
  if (row.unpaid_reason || row.status === 'past_due' || row.status === 'suspended') return 'unpaid';
  return null;
}

/**
 * The business whose card the bank declined when it has the same payer (the same Stripe customer) as `business`,
 * or `null`: the checkout says whose and asks for another card. Every business gets a payer of its own when it
 * is created, so another business's declined card is not this one's (audit 2 R-21).
 */
export function declinedCard(rows: readonly BusinessRowOut[], business: Pick<BusinessRowOut, 'payer_id'>): string | null {
  if (!business.payer_id) return null;
  const declined = rows.find(
    (row) => row.is_payer && row.payer_id === business.payer_id && row.unpaid_reason === 'card_declined',
  );
  return declined?.name ?? null;
}

/** A plan without a monthly price is Free: it is not bought, a paid plan is cancelled to get it. */
export function isFree(plan: Pick<PlanOut, 'price_monthly'>): boolean {
  return Number(plan.price_monthly) === 0;
}

/** The largest saving of paying a year instead of twelve months, in whole percent (0 = none). */
export function annualSaving(plans: readonly PlanOut[]): number {
  let best = 0;
  for (const plan of plans) {
    const year = Number(plan.price_monthly) * 12;
    const annual = Number(plan.price_annual);
    if (year > 0 && annual > 0 && annual < year) best = Math.max(best, Math.round((1 - annual / year) * 100));
  }
  return best;
}

/** The billing a module is bought at: the business's when Stripe bills it, monthly otherwise. */
export function moduleInterval(subscription: StoreSubscriptionOut | null | undefined): BillingInterval {
  return subscription?.paying ? subscription.billing_interval : 'month';
}
