// Invited, without a business of one's own, the entry's card is the invitation: accept and enter, decline, or create
// one's own. The page runs the acceptance and holds the decline dialog, so each button only hands its answer back.
import { describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { INVITATION } from '../__tests__/businesses';
import { INVITATION as INVITED, OPENED, page, setUpLaunchPage, showing } from '../__tests__/launch-page';
import { describeCall, flush, ionProps, mountHubs } from '../__tests__/mount-hubs';
import LaunchInvitation from './LaunchInvitation.vue';

setUpLaunchPage();

async function setup(accepting: string | null = null) {
  const m = await mountHubs(LaunchInvitation, { props: { invitation: INVITATION, accepting } });
  const button = (id: string) => m.wrapper.get(`[data-testid="${id}"]`);
  return { ...m, button };
}

describe('LaunchInvitation', () => {
  it('«Accept and enter» and «Decline» hand the invitation to the page', async () => {
    const s = await setup();
    expect(s.button('launch-accept').text()).toBe('Accept and enter');
    await s.button('launch-accept').trigger('click');
    await s.button('launch-decline').trigger('click');
    expect(s.wrapper.emitted('accept')).toEqual([[INVITATION]]);
    expect(s.wrapper.emitted('decline')).toEqual([[INVITATION]]);
  });

  it('«Create my own business» asks the page for the form', async () => {
    const s = await setup();
    await s.button('launch-create-own').trigger('click');
    expect(s.wrapper.emitted('createOwn')).toEqual([[]]);
    expect(s.wrapper.emitted('accept')).toBeUndefined();
  });

  it('while the page accepts it, «Accept and enter» spins and neither answer can be given again', async () => {
    const s = await setup(INVITATION.id);
    expect(s.button('launch-accept').find('ion-spinner').exists()).toBe(true);
    expect(['launch-accept', 'launch-decline', 'launch-create-own'].map((id) => ionProps(s.button(id), 'disabled'))).toEqual([
      { disabled: true },
      { disabled: true },
      { disabled: false },
    ]);
  });

  it('on the entry, «Accept and enter» keeps spinning while the business it joined opens', async () => {
    const s = await showing(page([], [INVITED]), {
      api: (call) => {
        const c = describeCall(call);
        if (c.path === '/api/hubs/invitations/accept') return Response.json({ ...INVITED.hub, can_open: true });
        return Response.json(c.path === '/api/hubs/businesses/open' ? OPENED : {});
      },
    });
    await s.testid('launch-accept').trigger('click');
    await flush();
    expect(s.opened()).toEqual([{ id: 'ana', next: '/' }]);
    expect(s.testid('launch-accept').find('ion-spinner').exists()).toBe(true);
  });

  it('on the entry, «Decline» opens the page’s confirmation', async () => {
    const s = await showing(page([], [INVITED]));
    const confirm = () => document.querySelector('[data-testid="decline-dialog-submit"]');
    expect(confirm()).toBeNull();
    await s.testid('launch-decline').trigger('click');
    await flush();
    expect(confirm()).not.toBeNull();
  });
});
