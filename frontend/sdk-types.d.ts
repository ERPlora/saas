// Types of the SaaS's operations for the SDK (`useLive`, `useCommand`, `client.api.call`).
// WRITTEN BY HAND for now from base/schemas.py, accounts/schemas.py and hubs/schemas.py (generated from
// `/api/openapi.json` later, as in hub-next). Keep it in step with `./generated/operations.json`.
// Dates and UUIDs travel as strings (ISO 8601). Sign-in is not an operation: the
// SDK reaches allauth.headless through `createAllauthClient`.
import type { SessionMe } from '@erplora/ui/shell';

/** `base.SessionMeIn`: no parameters. */
export type SessionMeIn = Record<string, never>;

/** `base.SessionPreferences`: what the account chose in Account → Preferences that the shell paints with. */
export interface SessionPreferences {
  theme_mode: AccountThemeMode;
}

/**
 * `base.SessionMeOut`: what the shell reads (`SessionMe`) plus the scope it was resolved for (the user) and
 * what the account chose (`null` without an account): its theme mode and its own language (`User.language`).
 */
export interface SessionMeOut extends SessionMe {
  scope: { kind: string; key: string };
  preferences: SessionPreferences | null;
  account_language: string | null;
}

/** `accounts.HubListIn`: no parameters (the account is the session's). */
export type HubListIn = Record<string, never>;

/** `accounts.HubOut`: a hub the account can enter, its host and the jump to it (`/hub-login/`). */
export interface HubOut {
  slug: string;
  host: string;
  url: string;
}

/** `accounts.HubListOut`: the account's hubs, alphabetically. */
export interface HubListOut {
  hubs: HubOut[];
}

// --- hubs (hubs/schemas.py): the businesses of an account, their members and invitations ---------

/** `hubs.Role`: a person's role in a business, from the most authority to the least. */
export type HubRole = 'hub_owner' | 'hub_admin' | 'hub_manager' | 'hub_employee';

/** `hubs.InvitableRole`: what an invitation or a role change may hand out (never the owner). */
export type InvitableRole = Exclude<HubRole, 'hub_owner'>;

/** `Hub.Status`: `deleted` (purged) is never listed. */
export type BusinessStatusCode = 'preparing' | 'active' | 'past_due' | 'suspended' | 'deleting';

/** Why «Open» does not work now (`BusinessRowOut.open_blocked_reason`). */
export type OpenBlockedReason = 'preparing' | 'error' | 'suspended' | 'deleting';

/** `hubs.UnpaidReason`: why a renewal is not paid. `card_declined`: «Pay» waits for another card. */
export type UnpaidReason = 'card_declined' | 'card_changed' | 'authentication_required' | 'payment_failed';

/** `hubs.PageIn`. */
export interface PageIn {
  limit?: number;
  offset?: number;
}

/** `hubs.Page[T]`. */
export interface Page<T> {
  rows: T[];
  total: number;
  limit: number;
  offset: number;
}

/** `hubs.ByIdIn`. */
export interface ByIdIn {
  id: string;
}

/** `hubs.HubRefOut`. */
export interface HubRefOut {
  id: string;
  slug: string;
  name: string;
}

/** `hubs.PlanRefOut`. */
export interface PlanRefOut {
  slug: string;
  name: string;
}

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
  upgrade_only: boolean;
  internal_only: boolean;
}

/** `hubs.PlanListOut`. */
export interface PlanListOut {
  signup_trial_days: number;
  cheapest_slug: string | null;
  plans: PlanOut[];
}

/** `hubs.BusinessListIn`. */
export interface BusinessListIn extends PageIn {
  search?: string;
}

/** `hubs.BusinessRowCanOut`: what a row's buttons do for this account, computed by the server. */
export interface BusinessRowCanOut {
  /** It serves now. */
  open: boolean;
  /** Owner and administrators, not deleted. */
  manage: boolean;
  /** The owner, deleted and within its 90 days. */
  restore: boolean;
  /** The owner, not deleted. */
  delete: boolean;
}

/** `hubs.BusinessRowOut`: a business the account belongs to (Businesses and the launcher). */
export interface BusinessRowOut {
  id: string;
  slug: string;
  name: string;
  host: string;
  status: BusinessStatusCode;
  status_label: string;
  plan: PlanRefOut | null;
  role: HubRole;
  role_label: string;
  last_opened_at: string | null;
  can_open: boolean;
  open_blocked_reason: OpenBlockedReason | null;
  hub_error: string | null;
  deletion_requested_at: string | null;
  purge_after: string | null;
  created_at: string;
  can: BusinessRowCanOut;
  /** Why a renewal is not paid; `null` while it is paid. */
  unpaid_reason: UnpaidReason | null;
  /** When the unpaid invoice was issued: the 7 days of grace count from it. */
  unpaid_since: string | null;
  /** Stripe's page to pay that invoice: only for the owner. */
  pay_url: string | null;
  /** The account owns the business's payer: it pays for it, whatever its role. */
  is_payer: boolean;
  /** That payer (its Stripe customer), only to whoever owns it (audit 2 R-21). */
  payer_id: string | null;
}

/** `hubs.InvitationOut`: an invitation waiting for this account's answer. */
export interface InvitationOut {
  id: string;
  hub: HubRefOut;
  role: HubRole;
  role_label: string;
  invited_by: string | null;
  invited_at: string | null;
  expires_at: string | null;
  message: string;
}

/** `hubs.OwnershipOfferOut`: a business offered to this account. */
export interface OwnershipOfferOut {
  id: string;
  hub: HubRefOut;
  from_email: string;
  expires_at: string;
}

/** `hubs.BusinessListOut`. */
export interface BusinessListOut extends Page<BusinessRowOut> {
  invitations: InvitationOut[];
  ownership_offers: OwnershipOfferOut[];
  /** The account's Free business when its Free ones fill the quota: «Create business» says so (audit 2 S-02). */
  free_business: HubRefOut | null;
}

/** `hubs.BusinessTypeRefOut`. */
export interface BusinessTypeRefOut {
  code: string;
  name: string;
}

/** `hubs.SeatsOut`: people on the business and what its plan covers (`limit` null = unlimited). */
export interface SeatsOut {
  used: number;
  limit: number | null;
}

/** `hubs.TransferRefOut`. */
export interface TransferRefOut {
  id: string;
  to_email: string;
  expires_at: string;
}

/** `hubs.BusinessCanOut`: what the account may do on the business, by its role. */
export interface BusinessCanOut {
  open: boolean;
  manage: boolean;
  manage_members: boolean;
  manage_settings: boolean;
  manage_billing: boolean;
  transfer: boolean;
  restore: boolean;
  delete: boolean;
}

/** `hubs.BusinessDetailOut`: a business's page (Summary and Settings). */
export interface BusinessDetailOut {
  id: string;
  slug: string;
  name: string;
  host: string;
  country: string;
  /** The country no longer changes: the business is ready and may invoice (409 `hubs.country_locked`). */
  country_locked: boolean;
  timezone: string;
  language: string;
  business_type: BusinessTypeRefOut | null;
  status: BusinessStatusCode;
  status_label: string;
  hub_error: string | null;
  ready_at: string | null;
  created_at: string;
  deletion_requested_at: string | null;
  purge_after: string | null;
  role: HubRole;
  role_label: string;
  plan: PlanRefOut | null;
  trial_plan: PlanRefOut | null;
  trial_end: string | null;
  seats: SeatsOut;
  pending_transfer: TransferRefOut | null;
  can: BusinessCanOut;
  /** Why a renewal is not paid; `null` while it is paid. */
  unpaid_reason: UnpaidReason | null;
  /** When the unpaid invoice was issued: the 7 days of grace count from it. */
  unpaid_since: string | null;
  /** Stripe's page to pay that invoice: only for the owner. */
  pay_url: string | null;
  /** The account owns the business's payer: it pays for it, whatever its role. */
  is_payer: boolean;
  /** The last day the Hub measured (`hubs.usage.get`); `null` until the first night (lot L4-A). */
  usage: UsageOut | null;
}

/** `hubs.AddressProposeIn`. */
export interface AddressProposeIn {
  name: string;
}

/** `hubs.AddressProposeOut`. */
export interface AddressProposeOut {
  slug: string;
  host: string;
}

/** `hubs.BusinessCreateIn`: a name, a country, and a business type if the person knows. */
export interface BusinessCreateIn {
  name: string;
  country: string;
  business_type?: string | null;
  slug?: string | null;
}

/** `hubs.BusinessUpdateIn`: only the fields sent change. */
export interface BusinessUpdateIn {
  id: string;
  name?: string;
  country?: string;
  language?: 'en' | 'es';
  timezone?: string;
}

/** `hubs.BusinessDeleteIn`. */
export interface BusinessDeleteIn {
  id: string;
  confirm_name: string;
}

/** `hubs.BusinessOpenIn`. */
export interface BusinessOpenIn {
  id: string;
  next?: string;
}

/** `hubs.BusinessOpenOut`: where «Open» goes, the Hub's start of the jump (`/auth/login?next=`), which
 *  binds it to the browser with its own `state`. The SPA navigates there. */
export interface BusinessOpenOut {
  url: string;
}

/** `hubs.MemberListIn`. */
export interface MemberListIn extends PageIn {
  hub_id: string;
}

/** `hubs.MemberAction`: what the account may do on a row of the members page. */
export type MemberAction = 'change_role' | 'remove' | 'resend' | 'cancel' | 'transfer';

/** `hubs.MemberRowOut`. */
export interface MemberRowOut {
  id: string;
  user_id: string;
  email: string;
  name: string;
  role: HubRole;
  role_label: string;
  status: 'active' | 'pending' | 'expired';
  status_label: string;
  invited_by: string | null;
  invited_at: string | null;
  invitation_expires_at: string | null;
  /** `null` while the invitation waits for its answer. */
  joined_at: string | null;
  accepted_at: string | null;
  last_opened_at: string | null;
  /** The account's own row. */
  is_me: boolean;
  /** What the account may do on this row, computed by the server, in this order (empty on its own
   *  row, a peer, a superior and a deleted business; `transfer` only for the owner). */
  actions: MemberAction[];
  /** The roles the account may give this member (empty without `change_role`). */
  assignable_roles: InvitableRole[];
}

/** `hubs.MemberListOut`. */
export interface MemberListOut extends Page<MemberRowOut> {
  seats: SeatsOut;
  invitable_roles: InvitableRole[];
}

/** `hubs.MemberInviteIn`. */
export interface MemberInviteIn {
  hub_id: string;
  email: string;
  role?: InvitableRole;
  message?: string;
}

/** `hubs.MemberRoleIn`. */
export interface MemberRoleIn {
  id: string;
  role: InvitableRole;
}

/** `hubs.RemovedOut`. */
export interface RemovedOut {
  id: string;
}

/** `hubs.InvitationListOut`. */
export interface InvitationListOut {
  invitations: InvitationOut[];
}

/** `hubs.OwnershipTransferIn`: the member the business is offered to. */
export interface OwnershipTransferIn {
  hub_id: string;
  member_id: string;
}

/** `hubs.OwnershipTransferOut`. */
export interface OwnershipTransferOut {
  id: string;
  hub: HubRefOut;
  from_email: string;
  to_email: string;
  status: 'pending' | 'accepted' | 'declined' | 'cancelled' | 'expired';
  expires_at: string;
  resolved_at: string | null;
}

// --- accounts (accounts/schemas.py): Account → Profile · Security · Preferences · API keys ----------

/** `accounts.ThemeMode`: the shell's theme mode (`ThemeMode` of `@erplora/ui/shell`). */
export type AccountThemeMode = 'system' | 'light' | 'dark';

/** `accounts.Language`: `settings.LANGUAGES` (English, the source, and Spanish). */
export type AccountLanguage = 'en' | 'es';

/** `accounts.PreferencesOut`: Account → Preferences. */
export interface PreferencesOut {
  theme_mode: AccountThemeMode;
  language: AccountLanguage;
  hub_alerts: boolean;
  marketing_emails: boolean;
}

/** `accounts.PreferencesUpdateIn`: only what is sent changes (each control saves on its own). */
export interface PreferencesUpdateIn {
  theme_mode?: AccountThemeMode;
  language?: AccountLanguage;
  hub_alerts?: boolean;
  marketing_emails?: boolean;
}

/** `accounts.ProfileOut`: Account → Profile. `photo` is a data URL or null (the initials). */
export interface ProfileOut {
  id: string;
  email: string;
  email_verified: boolean;
  /** The new address waiting for its code, asked for in this session. */
  pending_email: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  photo: string | null;
  has_password: boolean;
  date_joined: string;
}

/** `accounts.ProfileUpdateIn`. */
export interface ProfileUpdateIn {
  first_name: string;
  last_name: string;
}

/** `accounts.ProfileDeletedOut`. */
export interface ProfileDeletedOut {
  deleted: boolean;
}

/** `accounts.EmailChangeIn`. */
export interface EmailChangeIn {
  email: string;
}

/** `accounts.EmailVerifyIn`. */
export interface EmailVerifyIn {
  code: string;
}

/** `accounts.EmailVerifyOut`: a wrong code is no error, `verified` is false (0 tries left: ask again). */
export interface EmailVerifyOut {
  verified: boolean;
  attempts_left: number;
  profile: ProfileOut;
}

/** `accounts.PhotoUploadIn`: a JPEG, PNG or WebP as a `data:` URL. */
export interface PhotoUploadIn {
  image: string;
}

/** `accounts.SessionRowOut`: a signed-in browser or app; `device` is a code the panel names. */
export interface SessionRowOut {
  id: number;
  device: string;
  browser: string;
  browser_version: string;
  /** The app's version inside the ERPlora app (`browser` is then empty). */
  app_version: string | null;
  ip: string;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
}

/** `accounts.SessionListOut`: this session first. */
export interface SessionListOut {
  rows: SessionRowOut[];
  total: number;
}

/** `accounts.SessionCloseIn`. */
export interface SessionCloseIn {
  id: number;
}

/** `accounts.SessionsClosedOut`. */
export interface SessionsClosedOut {
  closed: number;
}

/** `accounts.ApiKeyRowOut`: a key of the account, never its secret. */
export interface ApiKeyRowOut {
  id: string;
  name: string;
  /** `erps_live_` and the first characters of the secret. */
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  expired: boolean;
}

/** `accounts.ApiKeyScopeOut`: a permission a key may get, with its label in the reader's language. */
export interface ApiKeyScopeOut {
  id: string;
  label: string;
}

/** `accounts.ApiKeyListOut`: the keys not revoked, the newest first, and the permissions on offer. */
export interface ApiKeyListOut {
  rows: ApiKeyRowOut[];
  total: number;
  scopes: ApiKeyScopeOut[];
}

/** `accounts.ApiKeyCreateIn`: 30 or 90 days, or null for a key that does not expire (90 by default). */
export interface ApiKeyCreateIn {
  name: string;
  scopes: string[];
  expires_in_days?: 30 | 90 | null;
}

/** `accounts.ApiKeyCreatedOut`: `secret` is the whole key, shown this once. */
export interface ApiKeyCreatedOut {
  key: ApiKeyRowOut;
  secret: string;
}

/** `accounts.ApiKeyRevokeIn`. */
export interface ApiKeyRevokeIn {
  id: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.session.me': { input: SessionMeIn; output: SessionMeOut };
    'accounts.hub.list': { input: HubListIn; output: HubListOut };
    'hubs.business_type.list': { input: BusinessTypeListIn | undefined; output: BusinessTypeListOut };
    'hubs.plan.list': { input: Record<string, never> | undefined; output: PlanListOut };
    'hubs.business.list': { input: BusinessListIn; output: BusinessListOut };
    'hubs.business.create': { input: BusinessCreateIn; output: BusinessDetailOut };
    'hubs.business.get': { input: ByIdIn; output: BusinessDetailOut };
    'hubs.business.update': { input: BusinessUpdateIn; output: BusinessDetailOut };
    'hubs.business.delete': { input: BusinessDeleteIn; output: BusinessDetailOut };
    'hubs.business.restore': { input: ByIdIn; output: BusinessDetailOut };
    'hubs.business.open': { input: BusinessOpenIn; output: BusinessOpenOut };
    'hubs.address.propose': { input: AddressProposeIn; output: AddressProposeOut };
    'hubs.member.list': { input: MemberListIn; output: MemberListOut };
    'hubs.member.invite': { input: MemberInviteIn; output: MemberRowOut };
    'hubs.member.change_role': { input: MemberRoleIn; output: MemberRowOut };
    'hubs.member.remove': { input: ByIdIn; output: RemovedOut };
    'hubs.member.resend': { input: ByIdIn; output: MemberRowOut };
    'hubs.member.cancel': { input: ByIdIn; output: RemovedOut };
    'hubs.invitation.list_mine': { input: Record<string, never> | undefined; output: InvitationListOut };
    'hubs.invitation.accept': { input: ByIdIn; output: BusinessRowOut };
    'hubs.invitation.decline': { input: ByIdIn; output: RemovedOut };
    'hubs.ownership.transfer': { input: OwnershipTransferIn; output: OwnershipTransferOut };
    'hubs.ownership.accept': { input: ByIdIn; output: OwnershipTransferOut };
    'hubs.ownership.decline': { input: ByIdIn; output: OwnershipTransferOut };
    'hubs.ownership.cancel': { input: ByIdIn; output: OwnershipTransferOut };
    'accounts.profile.get': { input: Record<string, never> | undefined; output: ProfileOut };
    'accounts.profile.update': { input: ProfileUpdateIn; output: ProfileOut };
    'accounts.profile.delete': { input: Record<string, never> | undefined; output: ProfileDeletedOut };
    'accounts.email.change': { input: EmailChangeIn; output: ProfileOut };
    'accounts.email.verify': { input: EmailVerifyIn; output: EmailVerifyOut };
    'accounts.photo.upload': { input: PhotoUploadIn; output: ProfileOut };
    'accounts.photo.remove': { input: Record<string, never> | undefined; output: ProfileOut };
    'accounts.preferences.get': { input: Record<string, never> | undefined; output: PreferencesOut };
    'accounts.preferences.update': { input: PreferencesUpdateIn; output: PreferencesOut };
    'accounts.session.list': { input: Record<string, never> | undefined; output: SessionListOut };
    'accounts.session.close': { input: SessionCloseIn; output: SessionsClosedOut };
    'accounts.session.close_others': { input: Record<string, never> | undefined; output: SessionsClosedOut };
    'accounts.apikey.list': { input: Record<string, never> | undefined; output: ApiKeyListOut };
    'accounts.apikey.create': { input: ApiKeyCreateIn; output: ApiKeyCreatedOut };
    'accounts.apikey.revoke': { input: ApiKeyRevokeIn; output: ApiKeyRowOut };
  }
}

// --- The Store (lot L2-D): billing (billing/schemas.py), the app catalog (apps/schemas.py) and the payer of
// a business (hubs/schemas.py `BillingProfile*`). Appended as its own block, with its own augmentation of
// `Operations` below (interfaces merge), so the lots that edit this file never touch the same lines. -----

/** `billing.Interval`: how a subscription is billed. */
export type BillingInterval = 'month' | 'year';

/** `billing.PromoCheckIn`. */
export interface PromoCheckIn {
  code: string;
}

/** `billing.PromoCheckOut`: whether the code grants a trial now, and how many days (0 when it does not). */
export interface PromoCheckOut {
  code: string;
  valid: boolean;
  trial_days: number;
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
}

/** `billing.StoreCatalogOut`. */
export interface StoreCatalogOut {
  hub_id: string;
  subscription: StoreSubscriptionOut | null;
  modules: StoreModuleOut[];
  /** The paid plans the business may move to: no upgrade-only plan while Stripe does not bill it (audit 2 S-03). */
  offered_plans: string[];
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
    'billing.module.cancel': { input: ModuleIn; output: SubscriptionOut };
    'billing.module.keep': { input: ModuleIn; output: SubscriptionOut };
  }
}

// --- The Billing section (lot L3-C front): ERPlora's invoices, the subscriptions and the payment details
// (billing/schemas.py). Its own block and its own augmentation of `Operations` below, as the Store's. --------

/** `billing.InvoicePaymentStatus`: not collected yet, paid, or cancelled in Stripe. */
export type InvoicePaymentStatus = 'open' | 'paid' | 'void';

/** `billing.InvoiceFiscalStatus`: what the platform hub says of it (`''` = not sent to it yet). */
export type InvoiceFiscalStatus = '' | 'issuing' | 'issued' | 'accepted' | 'accepted_with_errors' | 'rejected';

/** `billing.InvoiceRectificationType`: VeriFactu's `TipoFactura` of a rectifying invoice. */
export type InvoiceRectificationType = 'R1' | 'R2' | 'R3' | 'R4';

/** `billing.VatStatus`: the verdict a VAT number gets. */
export type VatStatus = 'verified' | 'invalid' | 'unavailable' | 'national' | 'outside_vies';

/** `billing.ScheduledChangeOut`: a plan change that starts with the next period (a downgrade). */
export interface ScheduledChangeOut {
  plan: string;
  interval: BillingInterval;
  starts_at: string;
}

/** The actions of an invoice row (`billing.InvoiceRowOut.actions`), the fixed one first. */
export type InvoiceAction = 'pay' | 'pdf';

/** The actions of a subscription row (`billing.SubscriptionRowOut.actions`), the fixed one first. */
export type SubscriptionAction = 'change_plan' | 'keep_plan' | 'view_invoice' | 'cancel_plan' | 'view_invoices';

/** `billing.InvoiceFilterIn`: a business, the payment, a year and part of a number (all optional). */
export interface InvoiceFilterIn {
  hub_id?: string | null;
  status?: InvoicePaymentStatus | null;
  year?: number | null;
  search?: string | null;
}

/** `billing.InvoiceListIn`. */
export interface InvoiceListIn extends InvoiceFilterIn {
  limit?: number;
  offset?: number;
}

/** `billing.InvoiceBusinessOut`: `id` is null once the business is gone; its name stays as invoiced. */
export interface InvoiceBusinessOut {
  id: string | null;
  name: string;
}

/** `billing.InvoiceCanOut`: what the row's buttons do for this account. */
export interface InvoiceCanOut {
  pay: boolean;
  pdf: boolean;
}

/** `billing.InvoiceRectificationOut`: why a credit note rectifies (`reason` empty when Stripe gave none). */
export interface InvoiceRectificationOut {
  type: InvoiceRectificationType;
  reason: string;
}

/** `billing.InvoiceRowOut`: one invoice of ERPlora (amounts in cents). */
export interface InvoiceRowOut {
  id: string;
  kind: 'invoice' | 'credit_note';
  kind_label: string;
  /** `null` until it is paid: an unpaid one has only Stripe's `reference`. */
  number: string | null;
  reference: string;
  /** The day (`YYYY-MM-DD`). */
  date: string;
  business: InvoiceBusinessOut;
  currency: string;
  net_cents: number;
  tax_cents: number;
  total_cents: number;
  payment_status: InvoicePaymentStatus;
  payment_status_label: string;
  fiscal_status: InvoiceFiscalStatus;
  fiscal_status_label: string;
  /** Why «Pay» waits: a declined card to change first, or another account pays it. */
  pay_blocked_reason: 'card_change_required' | 'payer_required' | null;
  /** The row's actions in order, the fixed one first. */
  actions: InvoiceAction[];
  can: InvoiceCanOut;
  /** `null` for an invoice; a credit note's type (R1–R4) and reason. */
  rectification: InvoiceRectificationOut | null;
  /** The Stripe object behind a credit note (`cn_…`, `re_…`); `''` for an invoice. */
  stripe_source_id: string;
}

/** `billing.InvoiceListOut`. */
export interface InvoiceListOut {
  rows: InvoiceRowOut[];
  total: number;
  limit: number;
  offset: number;
}

/** `billing.InvoiceByIdIn`. */
export interface InvoiceByIdIn {
  id: string;
}

/** `billing.InvoiceLineOut`. */
export interface InvoiceLineOut {
  position: number;
  description: string;
  item_kind: 'plan' | 'module' | 'other';
  item_slug: string;
  quantity: number;
  proration: boolean;
  period_start: string | null;
  period_end: string | null;
  tax_rate: string;
  net_cents: number;
  tax_cents: number;
  total_cents: number;
}

/** `billing.InvoiceRecipientOut`: the payer as it was on the issue date. */
export interface InvoiceRecipientOut {
  name: string;
  tax_id: string;
  address: string;
  city: string;
  postal_code: string;
  country: string;
  email: string;
}

/** `billing.InvoiceRefOut`. */
export interface InvoiceRefOut {
  id: string;
  number: string;
}

/** `billing.InvoiceDetailOut`: the row, its lines, its recipient and its QR. */
export interface InvoiceDetailOut extends InvoiceRowOut {
  issued_on: string | null;
  paid_at: string | null;
  tax_treatment: string;
  tax_country: string;
  tax_rate: string;
  recipient: InvoiceRecipientOut;
  lines: InvoiceLineOut[];
  rectifies: InvoiceRefOut | null;
  qr: string;
}

/** `billing.InvoicePayIn`. */
export interface InvoicePayIn {
  id: string;
}

/** `billing.InvoicePayOut`: Stripe's page to pay it. */
export interface InvoicePayOut {
  url: string;
}

/** `billing.SubscriptionListIn`. */
export interface SubscriptionListIn {
  limit?: number;
  offset?: number;
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
  /** `null` while the plan ends at the end of the period. */
  next_invoice: NextInvoiceOut | null;
  status: string;
  status_label: string;
  cancelling: boolean;
  ends_at: string | null;
  cancel_requested: boolean;
  unpaid_invoice_id: string | null;
  /** A downgrade waiting for the end of the period. */
  scheduled_change: ScheduledChangeOut | null;
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
    'billing.invoice.list': { input: InvoiceListIn | undefined; output: InvoiceListOut };
    'billing.invoice.get': { input: InvoiceByIdIn; output: InvoiceDetailOut };
    // A file (`Content-Disposition: attachment`): the browser downloads it (`billing/frontend/browser.ts`),
    // never `api.call`, which reads JSON.
    'billing.invoice.pdf': { input: InvoiceByIdIn; output: never };
    'billing.invoice.csv': { input: InvoiceFilterIn | undefined; output: never };
    'billing.invoice.pay': { input: InvoicePayIn; output: InvoicePayOut };
    'billing.subscription.list': { input: SubscriptionListIn | undefined; output: SubscriptionListOut };
    'billing.payment_method.get': { input: PaymentMethodIn | undefined; output: PaymentMethodOut };
    'billing.portal.open': { input: PortalOpenIn; output: PortalOpenOut };
    'billing.vat_check.run': { input: VatCheckIn; output: VatCheckOut };
  }
}

// --- The usage of a business (lot L4-A, PLAN-SAAS §5): hubs/schemas.py `*Usage*`, appended as its own block
// with its own augmentation of `Operations` (interfaces merge). A day travels as `YYYY-MM-DD` (UTC). -------

/** `hubs.StorageUsageOut`: the files (S3) against the space of the plan; `null` limit and percent without a plan. */
export interface StorageUsageOut {
  used_bytes: number;
  limit_bytes: number | null;
  /** Rounded; over 100 past the space of the plan. */
  percent: number | null;
}

/** `hubs.ActiveUsersOut`: the people active on the day measured and in the 30 days up to it. */
export interface ActiveUsersOut {
  on_day: number;
  last_30_days: number;
}

/** `hubs.UsageOut`: the last day the Hub measured; `stale` when it is not yesterday's (UTC). */
export interface UsageOut {
  day: string;
  storage: StorageUsageOut;
  active_users: ActiveUsersOut;
  stale: boolean;
}

/** `hubs.UsageGetIn`. */
export interface UsageGetIn {
  business_id: string;
}

/** `hubs.UsageSeriesIn`: the window, 1 to 365 days up to yesterday (30 by default). */
export interface UsageSeriesIn {
  business_id: string;
  days?: number;
}

/** `hubs.UsagePointOut`: one day measured of the window. */
export interface UsagePointOut {
  day: string;
  storage: StorageUsageOut;
  active_users: ActiveUsersOut;
}

/** `hubs.UsageSeriesOut`: the days measured of the window, oldest first, against the space of the plan today. */
export interface UsageSeriesOut {
  business_id: string;
  limit_bytes: number | null;
  points: UsagePointOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'hubs.usage.get': { input: UsageGetIn; output: UsageOut };
    'hubs.usage.series': { input: UsageSeriesIn; output: UsageSeriesOut };
  }
}
