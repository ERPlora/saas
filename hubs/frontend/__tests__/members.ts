// Rows of `hubs.member.list` for the members tests.
import type { MemberRowOut } from '../../../frontend/sdk-types';

export const member = (id: string, extra: Record<string, unknown> = {}): MemberRowOut =>
  ({
  id,
  user_id: `u-${id}`,
  email: `${id}@example.com`,
  name: id,
  role: 'hub_employee',
  role_label: 'Employee',
  status: 'active',
  status_label: 'Active',
  invited_by: null,
  invited_at: null,
  invitation_expires_at: null,
  joined_at: '2026-03-02T10:00:00Z',
  accepted_at: '2026-03-02T10:00:00Z',
  last_opened_at: null,
  is_me: false,
  actions: ['change_role', 'remove'],
  assignable_roles: ['hub_admin', 'hub_manager', 'hub_employee'],
    ...extra,
  }) as unknown as MemberRowOut;
