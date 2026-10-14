// The change of the sign-in email (accounts/README.md, «Correo por código propio»), in two steps of one dialog:
// the new address (`accounts.email.change`, which asks for a recent sign-in when it is another address), then the
// 6-digit code mailed to it, typed in this same session (`accounts.email.verify`). A wrong code is no error: the
// dialog says how many tries are left; with none, it asks for a new code. Proving the account's own address goes
// straight to the code.
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

import { fakeAllauth, ok } from '../__tests__/allauth-server';
import { type ApiCall, apiError, describeCall, flush, ionProps, mountPanel, profile, reauthRequired, typeInto } from '../__tests__/mount-panel';
import type { ProfileOut } from '../../../frontend/sdk-types';
import EmailChangeFlow from './EmailChangeFlow.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

type Mode = 'change' | 'verify' | 'resume';

async function setup(api: (call: ApiCall) => Response | Promise<Response>, mode: Mode = 'change', me: ProfileOut = profile()) {
  const open = ref(true);
  const Host = { render: () => h(EmailChangeFlow, { profile: me, mode, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }) };
  const s = await mountPanel(Host, { api });
  await flush();
  return { ...s, open };
}

const verified = (email: string) => Response.json({ verified: true, attempts_left: 2, profile: profile({ email }) });

describe('EmailChangeFlow', () => {
  it('asks for the new address, then sends the code there and asks for it', async () => {
    const s = await setup(() => Response.json(profile({ pending_email: 'laura@new.example' })));
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Change your email');
    expect(ionProps(s.q('email-change-address'), 'type', 'mode', 'fill', 'autocomplete')).toEqual({
      type: 'email',
      mode: 'md',
      fill: 'outline',
      autocomplete: 'email',
    });
    expect(ionProps(s.q('email-change-submit'), 'disabled')).toEqual({ disabled: true });
    await typeInto(s.q('email-change-address'), 'laura@new.example');
    s.q('email-change-submit')?.click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/email/change', { email: 'laura@new.example' }]]);
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Enter the code');
    expect(s.q('email-change')?.textContent).toContain('laura@new.example');
    expect(s.q('code')).not.toBeNull();
  });

  it('confirms it’s you first when the server asks, then sends the code', async () => {
    const server = fakeAllauth({ 'POST /auth/reauthenticate': ok({}) });
    let asked = 0;
    const s = await setup(() => (asked++ === 0 ? reauthRequired() : Response.json(profile({ pending_email: 'laura@new.example' }))));
    await typeInto(s.q('email-change-address'), 'laura@new.example');
    s.q('email-change-submit')?.click();
    await flush();
    expect(s.q('reauth-modal')?.querySelector('.ion-delegate-host')).not.toBeNull();
    expect(s.q('email-change-error')).toBeNull();
    await typeInto(s.q('reauth-password'), 'owner-secret');
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(server.callsTo('POST /auth/reauthenticate')).toHaveLength(1);
    expect(s.calls().map((c) => c.path)).toEqual(['/api/accounts/email/change', '/api/accounts/email/change']);
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Enter the code');
  });

  it('switches the account to the new address with the right code, says so and closes', async () => {
    const s = await setup((call) => (describeCall(call).path.endsWith('/verify') ? verified('laura@new.example') : Response.json(profile())));
    await typeInto(s.q('email-change-address'), 'laura@new.example');
    s.q('email-change-submit')?.click();
    await flush();
    await typeInto(s.q('code'), ' 123456 ');
    s.q('email-change-submit')?.click();
    await flush();
    expect(s.calls().at(-1)).toMatchObject({ path: '/api/accounts/email/verify', body: { code: '123456' } });
    expect(toastSuccess).toHaveBeenCalledWith('Your email is now laura@new.example');
    expect(s.open.value).toBe(false);
  });

  it('says a wrong code and the tries left; with none left, asks for a new code', async () => {
    let tries = 2;
    const s = await setup((call) =>
      describeCall(call).path.endsWith('/verify')
        ? Response.json({ verified: false, attempts_left: --tries, profile: profile() })
        : Response.json(profile()),
    );
    await typeInto(s.q('email-change-address'), 'laura@new.example');
    s.q('email-change-submit')?.click();
    await flush();
    await typeInto(s.q('code'), '000000');
    s.q('email-change-submit')?.click();
    await flush();
    expect(ionProps(s.q('code'), 'errorText')).toEqual({ errorText: 'That code is not right. Tries left: 1.' });
    s.q('email-change-submit')?.click();
    await flush();
    expect(s.q('email-change-error')?.textContent).toContain('That code no longer works: ask for a new one.');
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Change your email');
    expect(ionProps(s.q('email-change-address'), 'value')).toEqual({ value: 'laura@new.example' });
    expect(s.open.value).toBe(true);
  });

  it('sends a new code on demand', async () => {
    const s = await setup(() => Response.json(profile()));
    await typeInto(s.q('email-change-address'), 'laura@new.example');
    s.q('email-change-submit')?.click();
    await flush();
    s.q('email-change-resend')?.click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([
      ['/api/accounts/email/change', { email: 'laura@new.example' }],
      ['/api/accounts/email/change', { email: 'laura@new.example' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('We sent a new code to laura@new.example');
  });

  it('keeps a refusal in the dialog: a taken address under its field, too many codes on top', async () => {
    const answers = [
      apiError(422, 'invalid_payload', 'Invalid payload', { fields: { email: 'This email is already used by another account.' } }),
      apiError(429, 'accounts.too_many_codes', 'That address already got several codes in the last hour: try again later.'),
    ];
    const s = await setup(() => answers.shift()!);
    await typeInto(s.q('email-change-address'), 'carlos@example.com');
    s.q('email-change-submit')?.click();
    await flush();
    expect(ionProps(s.q('email-change-address'), 'errorText')).toEqual({ errorText: 'This email is already used by another account.' });
    s.q('email-change-submit')?.click();
    await flush();
    expect(s.q('email-change-error')?.textContent).toContain('several codes in the last hour');
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Change your email');
  });

  it('proves the account’s own address: the code goes there at once', async () => {
    const s = await setup(() => Response.json(profile({ email_verified: false })), 'verify', profile({ email_verified: false }));
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/email/change', { email: 'laura@example.com' }]]);
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Enter the code');
    expect(s.q('email-change')?.textContent).toContain('laura@example.com');
  });

  it('resumes a change waiting for its code without sending another', async () => {
    const s = await setup(() => Response.json(profile()), 'resume', profile({ pending_email: 'laura@new.example' }));
    expect(s.calls()).toEqual([]);
    expect(s.q('email-change')?.textContent).toContain('laura@new.example');
  });
});
