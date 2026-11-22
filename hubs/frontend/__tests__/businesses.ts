// Rows of `hubs.business.list` for the businesses tests: an active business on Starter that its owner opens, and what
// waits above the list for an answer: an invitation and an ownership offer.
export const business = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
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
  ...extra,
});

export const INVITATION = {
  id: 'm1',
  hub: { id: 'norte', slug: 'norte', name: 'Bar Norte' },
  role: 'hub_employee',
  role_label: 'Employee',
  invited_by: 'Pedro Sanz',
  invited_at: null,
  expires_at: null,
  message: '',
};
export const OFFER = { id: 't1', hub: { id: 'mar', slug: 'mar', name: 'Bar del Mar' }, from_email: 'pedro@example.com', expires_at: '2026-10-20T10:00:00Z' };
