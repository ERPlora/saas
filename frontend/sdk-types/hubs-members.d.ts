// hubs (hubs/schemas/): the members of a business, the invitations of an account and the hand-over of a
// business to another member.
import type {
  BusinessRowOut,
  ByIdIn,
  HubRefOut,
  HubRole,
  InvitableRole,
  InvitationOut,
  Page,
  PageIn,
  SeatsOut,
} from './hubs';

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
