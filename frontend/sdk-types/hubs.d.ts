// hubs (hubs/schemas/): the businesses of an account as they are listed, a business's page (Summary and
// Settings), and what the other hubs types share.
import type { UsageOut } from './hubs-usage';

/** `hubs.Role`: a person's role in a business, from the most authority to the least. */
export type HubRole = 'hub_owner' | 'hub_admin' | 'hub_manager' | 'hub_employee' | 'hub_accountant';

/** `hubs.InvitableRole`: what an invitation or a role change may hand out (never the owner). */
export type InvitableRole = Exclude<HubRole, 'hub_owner'>;

/** `Hub.Status`: `deleted` (purged) is never listed. */
export type BusinessStatusCode = 'preparing' | 'active' | 'past_due' | 'suspended' | 'deleting';

/** Why «Open» does not work now (`BusinessRowOut.open_blocked_reason`). */
export type OpenBlockedReason = 'preparing' | 'error' | 'suspended' | 'deleting';

/** `hubs.HubMaintenanceOut`: the real platform-wide pause from the Hub's signed status poll. */
export interface HubMaintenanceOut {
  frozen: boolean;
  reason: string;
  since: string | null;
}

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

/** `hubs.PlanRefOut`: the plan a business has (internal ones too), with what it covers. */
export interface PlanRefOut {
  slug: string;
  name: string;
  /** 0 is Free. */
  price_monthly: string;
  /** 0 = unlimited. */
  max_devices: number;
  /** 0 = unlimited. */
  max_apps: number;
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
  maintenance?: HubMaintenanceOut | null;
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
  /** That payer (its Stripe customer), only to whoever owns it. */
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
  /** The account's Free business when its Free ones fill the quota: «Create business» says so. */
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
  /** Only the owner moves the business to another web address (HUBS-F16). */
  change_address: boolean;
  /** Only the owner downloads the copies of the business's data (`hubs.data_copy.*`). */
  download_data: boolean;
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
  maintenance?: HubMaintenanceOut | null;
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
  /** The last day the Hub measured (`hubs.usage.get`); `null` until the first night. */
  usage: UsageOut | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'hubs.business.list': { input: BusinessListIn; output: BusinessListOut };
  }
}
