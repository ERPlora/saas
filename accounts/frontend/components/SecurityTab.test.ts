// Account → Security (mockups `account.html` «security»): the card «Sign-in» — password, two-step verification and
// Google, each a row — from the live `accounts.profile.get` (whether the account has a password), then the active
// sessions (SessionsTable).
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { fakeAllauth, ok } from '../__tests__/allauth-server';
import { errorFrame, flush, mountPanel, profile, subId } from '../__tests__/mount-panel';
import SecurityTab from './SecurityTab.vue';

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

async function setup() {
  fakeAllauth({ 'GET /account/authenticators': ok([]), 'GET /account/providers': ok([]) });
  const s = await mountPanel(SecurityTab);
  const stream = await s.live();
  return { ...s, stream };
}

describe('SecurityTab', () => {
  it('shows it is loading, then the rows of «Sign-in» and the sessions', async () => {
    const s = await setup();
    expect(s.q('security-loading')).not.toBeNull();
    expect(s.wrapper.text()).toContain('Active sessions');
    await s.result(s.stream, 'accounts.profile.get', profile({ has_password: true }));
    await flush();
    expect(s.q('security-loading')).toBeNull();
    expect(s.q('sign-in-card')?.textContent).toContain('Sign-in');
    expect(s.q('password-row-change')).not.toBeNull();
    expect(s.q('two-factor')).not.toBeNull();
    expect(s.q('google-row')).not.toBeNull();
  });

  it('is a `.panel-fill` stack: the sessions’ list takes the height the sign-in card leaves (Ioan, 2026-10-14)', async () => {
    const s = await setup();
    await s.result(s.stream, 'accounts.profile.get', profile({ has_password: true }));
    expect(s.wrapper.element.classList.contains('panel-fill')).toBe(true);
    expect(s.wrapper.element.querySelector(':scope > .data-table')).not.toBeNull();
  });

  it('offers to create a password to an account without one', async () => {
    const s = await setup();
    await s.result(s.stream, 'accounts.profile.get', profile({ has_password: false }));
    expect(s.q('password-row-create')).not.toBeNull();
  });

  it('says a failed load with «Retry»', async () => {
    const s = await setup();
    s.stream.push(errorFrame(subId(s.client, 'accounts.profile.get'), 'server_error'));
    await flush();
    expect(s.q('security-error')?.textContent).toContain('We could not load your account');
    expect(s.q('security-retry')).not.toBeNull();
  });
});
