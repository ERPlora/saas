// Account → Profile (mockups `account.html` «profile»): the live `accounts.profile.get` — loading, its failure
// with «Retry», then «Your details» (ProfileForm) and the danger card that deletes the account. A failure is
// said, never a skeleton for ever (audit 2026-10-14, R-08): an error of the query, or no answer in time.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { errorFrame, flush, HELLO, ionProps, LIVE_TIMEOUT_MS, mountPanel, profile, subId } from '../__tests__/mount-panel';
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
    expect(s.q('profile-loading')).toBeNull();
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    s.q('profile-retry')?.click();
    expect(reconnect).toHaveBeenCalled();
  });

  it('says a failed load, not a skeleton, when no answer comes in time (stream down, no network)', async () => {
    const s = await mountPanel(ProfileTab);
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.q('profile-error')?.textContent).toContain('We could not load your account');
    expect(s.q('profile-retry')?.textContent).toContain('Retry');
    expect(s.q('profile-loading')).toBeNull();
  });

  it('«Retry» opens the stream again and shows the account when it comes', async () => {
    const s = await mountPanel(ProfileTab);
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    s.q('profile-retry')?.click();
    await flush();
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.q('profile-error')).toBeNull();
    expect(s.q('profile-loading')).not.toBeNull();
    const stream = s.net.lastStream();
    stream.push(HELLO);
    await s.result(stream, 'accounts.profile.get', profile());
    expect(s.q('profile-loading')).toBeNull();
    expect(s.q('profile-email')?.textContent).toContain('laura@example.com');
  });

  it('opens the deletion from the danger card, on every surface', async () => {
    const s = await mountPanel(ProfileTab);
    const stream = await s.live();
    await s.result(stream, 'accounts.profile.get', profile());
    expect(s.q('profile-danger')?.textContent).toContain('Delete your account');
    // The danger card's businesses join the stream; deletion is on once none holds the account.
    const again = await s.live();
    await s.result(again, 'hubs.business.list', { rows: [], total: 0, limit: 100, offset: 0, invitations: [], ownership_offers: [] });
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: false });
    s.q('profile-delete')?.click();
    await flush();
    expect(s.q('delete-account')?.querySelector('.ion-delegate-host')).not.toBeNull();
  });

  it('offers «Download my data» between the details and the danger card (ACCOUNTS-F26)', async () => {
    const s = await mountPanel(ProfileTab);
    const stream = await s.live();
    await s.result(stream, 'accounts.profile.get', profile());
    const cards = [...document.querySelectorAll('[data-testid="profile-export-card"], [data-testid="profile-danger"]')];
    expect(cards.map((card) => card.getAttribute('data-testid'))).toEqual(['profile-export-card', 'profile-danger']);
    expect(s.q('profile-export')?.textContent?.trim()).toBe('Download my data');
  });
});
