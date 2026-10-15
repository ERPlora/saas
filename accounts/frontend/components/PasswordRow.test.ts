// The «Password» row of Account → Security, «Sign-in» (mockups `account.html` «security»): «Change password» opens
// its dialog; an account that only signs in with Google has none, and the server never sets one with the session
// alone (`accounts/doors.py`), so it gets one through «Forgot your password?», the email link (the SPA's `/password/reset`).
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { flush, ionProps, mountPanel } from '../__tests__/mount-panel';
import PasswordRow from './PasswordRow.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('PasswordRow', () => {
  it('opens «Change password» for an account with one', async () => {
    const s = await mountPanel(PasswordRow, { props: { hasPassword: true, email: 'laura@example.com' } });
    await flush();
    expect(s.q('password-row')?.textContent).toContain('Password');
    s.q('password-row-change')?.click();
    await flush();
    expect(s.q('password-change')?.querySelector('.ion-delegate-host')).not.toBeNull();
  });

  it('sends an account without one to get it by email', async () => {
    const s = await mountPanel(PasswordRow, { props: { hasPassword: false, email: 'laura@example.com' } });
    await flush();
    expect(s.q('password-row')?.textContent).toContain('no password yet');
    expect(s.q('password-row-change')).toBeNull();
    // The SPA's page, opened inside the SPA (Ionic Vue's router link also renders its href): no longer
    // allauth's template page.
    expect(s.q('password-row-create')?.getAttribute('routerlink')).toBe('/password/reset');
    expect(ionProps(s.q('password-row-create'), 'href')).toEqual({ href: '/password/reset' });
    expect(s.q('password-row-create')?.textContent).toContain('Create a password');
  });
});
