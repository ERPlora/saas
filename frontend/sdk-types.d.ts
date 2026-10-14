// Types of the SaaS's operations for the SDK (`useLive`, `useCommand`, `client.api.call`).
// WRITTEN BY HAND for now from base/schemas.py, accounts/schemas.py and hubs/schemas.py (generated from
// `/api/openapi.json` later, as in hub-next). Keep it in step with `./generated/operations.json`.
// Dates and UUIDs travel as strings (ISO 8601). Sign-in is not an operation: the
// SDK reaches allauth.headless through `createAllauthClient`.
import type { SessionMe } from '@erplora/ui/shell';

/** `base.SessionMeIn`: no parameters. */
export type SessionMeIn = Record<string, never>;

/** `base.SessionMeOut`: what the shell reads (`SessionMe`) plus the scope it was resolved for (the user). */
export interface SessionMeOut extends SessionMe {
  scope: { kind: string; key: string };
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
  }
}
