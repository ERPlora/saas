// Account → Profile, «Your details» (mockups `account.html` «profile»): the photo, first and last name (saved with
// «Save changes», which waits for a change), and the email the account signs in with, changed only through its
// code (EmailChangeFlow). An address never proven says so and offers to prove it; a change waiting for its code
// offers to type it.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { apiError, flush, ionProps, mountPanel, profile, typeInto } from '../__tests__/mount-panel';
import type { ProfileOut } from '../../../frontend/sdk-types';
import ProfileForm from './ProfileForm.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

async function setup(me: ProfileOut = profile(), api: () => Response | Promise<Response> = () => Response.json(profile())) {
  const s = await mountPanel(ProfileForm, { props: { profile: me }, api });
  await flush();
  return s;
}

describe('ProfileForm', () => {
  it('paints the account: its avatar, its names and the email it signs in with', async () => {
    const s = await setup();
    expect(s.q('profile-avatar')?.getAttribute('aria-label')).toBe('Laura Martín Pérez');
    // The account header's avatar (mockups `.avatar.is-lg`, 72 px).
    expect(s.q('profile-avatar')?.getAttribute('data-size')).toBe('xl');
    expect(ionProps(s.q('profile-first-name'), 'value', 'mode', 'fill', 'autocomplete')).toEqual({
      value: 'Laura',
      mode: 'md',
      fill: 'outline',
      autocomplete: 'given-name',
    });
    expect(ionProps(s.q('profile-last-name'), 'value', 'autocomplete')).toEqual({ value: 'Martín Pérez', autocomplete: 'family-name' });
    expect(s.q('profile-email')?.textContent).toContain('laura@example.com');
    expect(s.q('profile-email-unverified')).toBeNull();
  });

  it('waits for a change before «Save changes», then saves the names and says so', async () => {
    const s = await setup(profile(), () => Response.json(profile({ first_name: 'Laura M.', full_name: 'Laura M. Martín Pérez' })));
    expect(ionProps(s.q('profile-save'), 'disabled')).toEqual({ disabled: true });
    await typeInto(s.q('profile-first-name'), 'Laura M.');
    expect(ionProps(s.q('profile-save'), 'disabled')).toEqual({ disabled: false });
    s.q('profile-save')?.click();
    await flush();
    expect(s.calls().map((c) => [c.method, c.path, c.body])).toEqual([
      ['POST', '/api/accounts/profile', { first_name: 'Laura M.', last_name: 'Martín Pérez' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Changes saved');
  });

  it('the first name is required: blank, it is said under the field and nothing is saved (audit 2 S-10)', async () => {
    const s = await setup();
    await typeInto(s.q('profile-first-name'), '   ');
    expect(ionProps(s.q('profile-save'), 'disabled')).toEqual({ disabled: true });
    expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Write your first name.' });
    expect(s.q('profile-first-name')?.classList.contains('ion-invalid')).toBe(true);
    s.q('profile-save')?.click();
    await flush();
    expect(s.calls()).toEqual([]);
    // The last name may be cleared.
    await typeInto(s.q('profile-first-name'), 'Laura');
    await typeInto(s.q('profile-last-name'), '');
    expect(ionProps(s.q('profile-save'), 'disabled')).toEqual({ disabled: false });
  });

  describe('an account with no first name yet: the field says it once the person has been in it or changed the form, never on opening', () => {
    const nameless = () => profile({ first_name: '', full_name: 'Martín Pérez' });
    /** The person leaves the field, as a tab or a click elsewhere does (Ionic's `ionBlur`). */
    async function leave(el: Element | null): Promise<void> {
      if (!el) throw new Error('no field');
      el.dispatchEvent(new CustomEvent('ionBlur'));
      await flush();
    }
    const marked = (el: Element | null) => ['ion-invalid', 'ion-touched'].filter((c) => el?.classList.contains(c));
    /** The text under the field; Vue leaves `''` where an error text was. */
    const said = (el: Element | null) => (ionProps(el, 'errorText').errorText as string | undefined) || '';

    it('opening the profile says nothing yet, and «Save changes» still waits for the name', async () => {
      const s = await setup(nameless());
      expect(said(s.q('profile-first-name'))).toBe('');
      expect(marked(s.q('profile-first-name'))).toEqual([]);
      expect(ionProps(s.q('profile-save'), 'disabled')).toEqual({ disabled: true });
    });

    it('leaving the field empty says it under the field', async () => {
      const s = await setup(nameless());
      await leave(s.q('profile-first-name'));
      expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Write your first name.' });
      expect(marked(s.q('profile-first-name'))).toEqual(['ion-invalid', 'ion-touched']);
    });

    it('writing only spaces says it under the field', async () => {
      const s = await setup(nameless());
      await typeInto(s.q('profile-first-name'), '  ');
      expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Write your first name.' });
      expect(marked(s.q('profile-first-name'))).toEqual(['ion-invalid', 'ion-touched']);
    });

    it('trying to save says it under the field and saves nothing', async () => {
      const s = await setup(nameless());
      await typeInto(s.q('profile-last-name'), 'Gómez');
      s.q('profile-save')?.click();
      await flush();
      expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Write your first name.' });
      expect(marked(s.q('profile-first-name'))).toEqual(['ion-invalid', 'ion-touched']);
      expect(s.calls()).toEqual([]);
    });

    it('leaving the field with a name written says nothing', async () => {
      const s = await setup(nameless());
      await typeInto(s.q('profile-first-name'), 'Jorge');
      await leave(s.q('profile-first-name'));
      expect(said(s.q('profile-first-name'))).toBe('');
      expect(marked(s.q('profile-first-name'))).toEqual([]);
      expect(ionProps(s.q('profile-save'), 'disabled')).toEqual({ disabled: false });
    });

    it('changing only the last name says why «Save changes» stays off', async () => {
      const s = await setup(profile({ first_name: '', last_name: '', full_name: '' }));
      await typeInto(s.q('profile-last-name'), 'Gómez');
      expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Write your first name.' });
      expect(marked(s.q('profile-first-name'))).toEqual(['ion-invalid', 'ion-touched']);
      expect(ionProps(s.q('profile-save'), 'disabled')).toEqual({ disabled: true });
    });

    it('in Spanish, changing only the last name: «Escribe tu nombre.»', async () => {
      const s = await mountPanel(ProfileForm, { props: { profile: profile({ first_name: '', last_name: '', full_name: '' }) }, locale: 'es' });
      await flush();
      await typeInto(s.q('profile-last-name'), 'Gómez');
      expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Escribe tu nombre.' });
      expect(marked(s.q('profile-first-name'))).toEqual(['ion-invalid', 'ion-touched']);
    });

    it('in Spanish, once left empty: «Escribe tu nombre.»', async () => {
      const s = await mountPanel(ProfileForm, { props: { profile: nameless() }, locale: 'es' });
      await flush();
      expect(marked(s.q('profile-first-name'))).toEqual([]);
      await leave(s.q('profile-first-name'));
      expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Escribe tu nombre.' });
    });
  });

  it('says a refused name under its field', async () => {
    const s = await setup(profile(), () =>
      apiError(422, 'invalid_payload', 'Invalid payload', { fields: { first_name: 'Ensure this value has at most 150 characters.' } }),
    );
    await typeInto(s.q('profile-first-name'), 'x'.repeat(151));
    s.q('profile-save')?.click();
    await flush();
    expect(ionProps(s.q('profile-first-name'), 'errorText')).toEqual({ errorText: 'Ensure this value has at most 150 characters.' });
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('says a lost connection in a toast, in the person’s language', async () => {
    const s = await setup(profile(), () => Promise.reject(new TypeError('Failed to fetch')) as never);
    await typeInto(s.q('profile-last-name'), 'Martín');
    s.q('profile-save')?.click();
    await flush();
    expect(toastError).toHaveBeenCalledWith('We could not reach ERPlora. Check your connection and try again.');
  });

  it('follows the account when it changes elsewhere (another tab), unless the person is typing', async () => {
    const s = await setup();
    await s.wrapper.setProps({ profile: profile({ first_name: 'Lau' }) });
    expect(ionProps(s.q('profile-first-name'), 'value')).toEqual({ value: 'Lau' });
    await typeInto(s.q('profile-last-name'), 'Gómez');
    await s.wrapper.setProps({ profile: profile({ first_name: 'L' }) });
    expect(ionProps(s.q('profile-last-name'), 'value')).toEqual({ value: 'Gómez' });
  });

  it('opens the change of email in its dialog', async () => {
    const s = await setup();
    s.q('profile-email-change')?.click();
    await flush();
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Change your email');
  });

  it('says an address never proven and offers to prove it with a code', async () => {
    const s = await setup(profile({ email_verified: false }), () => Response.json(profile({ email_verified: false })));
    expect(s.q('profile-email-unverified')?.textContent).toContain('Not verified');
    s.q('profile-email-verify')?.click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/email/change', { email: 'laura@example.com' }]]);
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Enter the code');
  });

  it('offers to type the code of a change waiting for it', async () => {
    const s = await setup(profile({ pending_email: 'laura@new.example' }));
    expect(s.q('profile-email-pending')?.textContent).toContain('laura@new.example');
    s.q('profile-email-pending-code')?.click();
    await flush();
    expect(s.q('email-change')?.getAttribute('aria-label')).toBe('Enter the code');
    expect(s.q('email-change')?.textContent).toContain('laura@new.example');
  });
});
