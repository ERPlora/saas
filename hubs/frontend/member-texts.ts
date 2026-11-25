// What the Members of a business say of its plan and its end. ERPlora's own business (`is_platform`) has no plan and
// nobody deletes it: there they speak of neither.

/** The texts (i18n keys) of Members that depend on the business. */
export interface MemberTexts {
  /** What each role may do, a line each. */
  roles: readonly string[];
  /** That the accountancy firm takes no place of the plan. */
  freeRole: string | null;
  /** What a transfer does to a paid plan. */
  transferBilling: string | null;
}

const CUSTOMER: MemberTexts = {
  roles: ['hubs.members.rolesOwner', 'hubs.members.rolesAdmin', 'hubs.members.rolesStaff', 'hubs.members.rolesAccountant'],
  freeRole: 'hubs.members.inviteModal.freeRole',
  transferBilling: 'hubs.members.transfer.consequenceBilling',
};

const PLATFORM: MemberTexts = {
  roles: [
    'hubs.members.platform.rolesOwner',
    'hubs.members.rolesAdmin',
    'hubs.members.rolesStaff',
    'hubs.members.platform.rolesAccountant',
  ],
  freeRole: null,
  transferBilling: null,
};

export function memberTexts(business: { is_platform: boolean } | undefined): MemberTexts {
  return business?.is_platform ? PLATFORM : CUSTOMER;
}
