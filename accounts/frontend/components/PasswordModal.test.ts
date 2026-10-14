// «Change password» (mockups `account.html` «security», «Contraseña»): the current password and the new one, with a
// hint of its strength while it is typed, over allauth.headless (`account/password/change`). allauth's refusals go
// under their field; a change that signs the session out leaves for the sign-in.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { anonymous, type Answer, fakeAllauth, rejected, signedIn } from '../__tests__/allauth-server';
import { flush, ionProps, mountPanel, typeInto } from '../__tests__/mount-panel';
import PasswordModal from './PasswordModal.vue';

const leave = vi.fn();

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  leave.mockClear();
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

async function setup(answer: Answer | Answer[] = signedIn, locale: 'en' | 'es' = 'en') {
  const server = fakeAllauth({ 'POST /account/password/change': answer });
  const open = ref(true);
  const Host = {
    render: () => h(PasswordModal, { email: 'laura@example.com', leave, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }),
  };
  const s = await mountPanel(Host, { locale });
  await flush();
  return { ...s, server, open };
}

async function fill(s: Awaited<ReturnType<typeof setup>>, current = 'old-secret-1', next = 'Pan-de-centeno-26') {
  await typeInto(s.q('password-current'), current);
  await typeInto(s.q('password-new'), next);
}

describe('PasswordModal', () => {
  it('asks for the current password and the new one, as a password manager expects', async () => {
    const s = await setup();
    expect(s.q('password-change')?.getAttribute('aria-label')).toBe('Change your password');
    expect(ionProps(s.q('password-current'), 'type', 'mode', 'fill', 'autocomplete')).toEqual({
      type: 'password',
      mode: 'md',
      fill: 'outline',
      autocomplete: 'current-password',
    });
    expect(ionProps(s.q('password-new'), 'type', 'autocomplete')).toEqual({ type: 'password', autocomplete: 'new-password' });
    expect(ionProps(s.q('password-change-submit'), 'disabled')).toEqual({ disabled: true });
  });

  it('hints how strong the new password looks while it is typed', async () => {
    const s = await setup();
    await typeInto(s.q('password-new'), 'abc');
    expect(ionProps(s.q('password-new'), 'helperText')).toEqual({ helperText: 'Too short: at least 8 characters.' });
    await typeInto(s.q('password-new'), 'laura-panaderia');
    expect(ionProps(s.q('password-new'), 'helperText')).toEqual({ helperText: 'Weak: avoid your email and use several kinds of characters.' });
    await typeInto(s.q('password-new'), 'Pan-de-centeno-26');
    expect(ionProps(s.q('password-new'), 'helperText')).toEqual({ helperText: 'Strong.' });
  });

  it('changes it, says so and closes', async () => {
    const s = await setup();
    await fill(s);
    s.q('password-change-submit')?.click();
    await flush();
    expect(s.server.callsTo('POST /account/password/change').map((call) => call.body)).toEqual([
      { current_password: 'old-secret-1', new_password: 'Pan-de-centeno-26' },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Password changed. Your businesses will ask you to sign in again.');
    expect(s.open.value).toBe(false);
    expect(leave).not.toHaveBeenCalled();
  });

  it('says a wrong current password and a refused new one under their fields', async () => {
    const s = await setup([rejected('Please type your current password.', 'current_password'), rejected('This password is too common.', 'new_password')]);
    await fill(s);
    s.q('password-change-submit')?.click();
    await flush();
    expect(ionProps(s.q('password-current'), 'errorText')).toEqual({ errorText: 'Please type your current password.' });
    s.q('password-change-submit')?.click();
    await flush();
    expect(ionProps(s.q('password-new'), 'errorText')).toEqual({ errorText: 'This password is too common.' });
    expect(s.open.value).toBe(true);
  });

  it('leaves for the sign-in when the change ends the session', async () => {
    const s = await setup(anonymous);
    await fill(s);
    s.q('password-change-submit')?.click();
    await flush();
    expect(leave).toHaveBeenCalledWith('/login');
  });

  it('speaks Spanish', async () => {
    const s = await setup(signedIn, 'es');
    expect(s.q('password-change')?.getAttribute('aria-label')).toBe('Cambiar tu contraseña');
  });
});
