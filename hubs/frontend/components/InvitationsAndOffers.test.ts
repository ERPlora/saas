// What waits above the businesses list for the account's answer, on its own: a notice per pending invitation and
// per ownership offer. Accepting runs its command here; declining an invitation is handed to the page, which holds
// the confirmation.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'vue';

vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import { INVITATION, OFFER } from '../__tests__/businesses';
import { flush, mountHubs } from '../__tests__/mount-hubs';
import InvitationsAndOffers from './InvitationsAndOffers.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(invitations: unknown[], offers: unknown[]) {
  const declined = vi.fn();
  const Host = { render: () => h(InvitationsAndOffers, { invitations: invitations as never, offers: offers as never, onDecline: declined }) };
  const m = await mountHubs(Host, {
    api: (call) => Response.json(call.url.includes('/ownership/') ? { id: 't1', hub: OFFER.hub, status: 'accepted' } : {}),
  });
  const notices = () => m.wrapper.findAll('[data-testid^="businesses-"]').map((notice) => notice.attributes('data-testid'));
  return { ...m, declined, notices };
}

describe('InvitationsAndOffers', () => {
  it('shows a notice per invitation and per offer, invitations first, and nothing without any', async () => {
    const s = await setup([INVITATION, { ...INVITATION, id: 'm2', invited_by: '' }], [OFFER]);
    expect(s.notices()).toEqual(['businesses-invitation-m1', 'businesses-invitation-m2', 'businesses-offer-t1']);
    const withoutInviter = s.wrapper.get('[data-testid="businesses-invitation-m2"]').text();
    expect([withoutInviter.includes('Pedro Sanz'), withoutInviter.includes('Employee')]).toEqual([false, true]);
    const none = await setup([], []);
    expect(none.notices()).toEqual([]);
  });

  it('«Decline» on an invitation hands it to the page and runs nothing', async () => {
    const s = await setup([INVITATION], []);
    await s.wrapper.get('[data-testid="invitation-decline"]').trigger('click');
    await flush();
    expect(s.declined.mock.calls).toEqual([[INVITATION]]);
    expect(s.calls()).toEqual([]);
  });

  it('accepting an ownership offer runs hubs.ownership.accept and says so', async () => {
    const s = await setup([], [OFFER]);
    await s.wrapper.get('[data-testid="offer-accept"]').trigger('click');
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/ownership/accept', { id: 't1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('You are now the owner of Bar del Mar');
  });
});
