// Account → Security, the «Two-step verification» row of «Sign-in» (mockups `account.html` «security»): whether it
// is on (allauth.headless `account/authenticators`) and the way to its settings (`/2fa`). With 2FA switched off on
// the server (`ACCOUNTS_MFA_ENABLED`: its endpoints answer 404) there is nothing to manage and the row is not painted.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fakeAllauth, json, notFound, ok } from '../__tests__/allauth-server';
import { flush, mountPanel } from '../__tests__/mount-panel';
import TwoFactorRow from './TwoFactorRow.vue';

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('TwoFactorRow', () => {
  it('says two-step verification is on and leads to its settings', async () => {
    fakeAllauth({ 'GET /account/authenticators': ok([{ type: 'totp', created_at: 1, last_used_at: null }]) });
    const s = await mountPanel(TwoFactorRow);
    await flush();
    expect(s.q('two-factor')?.textContent).toContain('Two-step verification');
    expect(s.q('two-factor')?.classList.contains('card-row')).toBe(true);
    expect(s.q('two-factor-state')?.textContent).toContain('On');
    expect(s.q('two-factor-manage')?.textContent).toContain('Manage');
    s.q('two-factor-manage')?.click();
    await flush();
    expect(s.router.currentRoute.value.fullPath).toBe('/2fa');
  });

  it('says it is off and offers to set it up', async () => {
    fakeAllauth({ 'GET /account/authenticators': ok([]) });
    const s = await mountPanel(TwoFactorRow);
    await flush();
    expect(s.q('two-factor-state')?.textContent).toContain('Off');
    expect(s.q('two-factor-manage')?.textContent).toContain('Set up');
  });

  it('is not painted when 2FA is switched off on the server', async () => {
    fakeAllauth({ 'GET /account/authenticators': notFound });
    const s = await mountPanel(TwoFactorRow);
    await flush();
    expect(s.q('two-factor')).toBeNull();
  });

  it('asks nothing when spa-config already says 2FA is switched off, and paints nothing', async () => {
    const server = fakeAllauth({ 'GET /account/authenticators': notFound });
    const s = await mountPanel(TwoFactorRow, { config: { mfaEnabled: false } });
    await flush();
    expect(server.callsTo('GET /account/authenticators')).toEqual([]);
    expect(s.q('two-factor')).toBeNull();
  });

  it('asks when spa-config says 2FA is switched on', async () => {
    const server = fakeAllauth({ 'GET /account/authenticators': ok([]) });
    const s = await mountPanel(TwoFactorRow, { config: { mfaEnabled: true } });
    await flush();
    expect(server.callsTo('GET /account/authenticators')).toHaveLength(1);
    expect(s.q('two-factor-state')?.textContent).toContain('Off');
  });

  it('still leads to the settings when the state cannot be read', async () => {
    fakeAllauth({ 'GET /account/authenticators': () => json(500, { status: 500 }) });
    const s = await mountPanel(TwoFactorRow);
    await flush();
    expect(s.q('two-factor-state')).toBeNull();
    expect(s.q('two-factor-manage')?.textContent).toContain('Manage');
  });
});
