// Invited, without a business of one's own, the entry's card is the invitation: accept and enter, decline, or create
// one's own. The page runs the acceptance and holds the decline dialog, so each button only hands its answer back.
import { afterEach, describe, expect, it } from 'vitest';

import { INVITATION } from '../__tests__/businesses';
import { ionProps, mountHubs } from '../__tests__/mount-hubs';
import LaunchInvitation from './LaunchInvitation.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

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
});
