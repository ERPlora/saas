// Account → Profile (mockups `account.html` «profile»): the live `accounts.profile.get` — loading, its failure
// with «Retry», then «Your details» (ProfileForm) and the danger card that deletes the account.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { errorFrame, flush, mountPanel, profile, subId } from '../__tests__/mount-panel';
import ProfileTab from './ProfileTab.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('ProfileTab', () => {
  it('shows it is loading, then the account', async () => {
    const s = await mountPanel(ProfileTab);
    const stream = await s.live();
    expect(s.q('profile-loading')).not.toBeNull();
    expect(s.q('profile-card')).toBeNull();
    await s.result(stream, 'accounts.profile.get', profile());
    expect(s.q('profile-loading')).toBeNull();
    expect(s.q('profile-email')?.textContent).toContain('laura@example.com');
  });

  it('says a failed load and tries again', async () => {
    const s = await mountPanel(ProfileTab);
    const stream = await s.live();
    stream.push(errorFrame(subId(s.client, 'accounts.profile.get'), 'server_error'));
    await flush();
    expect(s.q('profile-error')?.textContent).toContain('We could not load your account');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    s.q('profile-retry')?.click();
    expect(reconnect).toHaveBeenCalled();
  });

  it('opens the deletion from the danger card, on every surface', async () => {
    const s = await mountPanel(ProfileTab);
    const stream = await s.live();
    await s.result(stream, 'accounts.profile.get', profile());
    expect(s.q('profile-danger')?.textContent).toContain('Delete your account');
    s.q('profile-delete')?.click();
    await flush();
    expect(s.q('delete-account')?.querySelector('.ion-delegate-host')).not.toBeNull();
  });
});
