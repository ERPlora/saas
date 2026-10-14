// «Delete account» (mockups `account.html`, the danger card of Profile; Google Play asks for it in the apps too):
// a ConfirmDialog that waits for the account's email typed, then `accounts.profile.delete`. A business the account
// owns or pays for holds it (409, with the businesses): the dialog names each one with a link to its Settings. The
// server may ask «Confirm it's you» first. Deleted, the session is gone: the page leaves for the public web.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { fakeAllauth, ok } from '../__tests__/allauth-server';
import { apiError, flush, ionProps, mountPanel, profile, reauthRequired, typeInto } from '../__tests__/mount-panel';
import DeleteAccountDialog from './DeleteAccountDialog.vue';

const leave = vi.fn();

afterEach(() => {
  leave.mockClear();
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

async function setup(api: () => Response | Promise<Response>) {
  const open = ref(true);
  const Host = {
    render: () =>
      h(DeleteAccountDialog, { profile: profile(), leave, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }),
  };
  const s = await mountPanel(Host, { api });
  await flush();
  return { ...s, open };
}

async function confirmWithEmail(s: Awaited<ReturnType<typeof setup>>) {
  await typeInto(s.q('delete-account-input')?.querySelector('ion-input') ?? s.q('delete-account-input'), 'laura@example.com');
  s.q('delete-account-submit')?.click();
  await flush();
}

describe('DeleteAccountDialog', () => {
  it('says what goes and waits for the account’s email typed before deleting', async () => {
    const s = await setup(() => Response.json({ deleted: true }));
    expect(s.q('delete-account')?.getAttribute('aria-label')).toBe('Delete your account');
    expect(s.q('delete-account')?.getAttribute('role')).toBe('alertdialog');
    expect(s.q('delete-account')?.textContent).toContain('This cannot be undone');
    expect(ionProps(s.q('delete-account-submit'), 'disabled')).toEqual({ disabled: true });
  });

  it('deletes the account and leaves for the public web', async () => {
    const s = await setup(() => Response.json({ deleted: true }));
    await confirmWithEmail(s);
    expect(s.calls().map((c) => [c.method, c.path])).toEqual([['POST', '/api/accounts/profile/delete']]);
    expect(leave).toHaveBeenCalledWith('/');
  });

  it('names the businesses that hold the account, each linked to its Settings', async () => {
    const s = await setup(() =>
      apiError(409, 'accounts.owns_businesses', 'You own businesses: transfer or delete them before deleting your account.', {
        businesses: [
          { id: 'b1', name: 'Panadería López' },
          { id: 'b2', name: 'Café Central' },
        ],
      }),
    );
    await confirmWithEmail(s);
    expect(s.q('delete-account-blocked')?.textContent).toContain('You own businesses');
    const links = [...document.querySelectorAll('[data-testid="delete-account-business"]')];
    expect(links.map((a) => [a.textContent?.trim(), a.getAttribute('href')])).toEqual([
      ['Panadería López', '/businesses/b1/settings'],
      ['Café Central', '/businesses/b2/settings'],
    ]);
    expect(leave).not.toHaveBeenCalled();
    expect(s.open.value).toBe(true);
  });

  it('asks «Confirm it’s you» when the server wants it, then deletes', async () => {
    fakeAllauth({ 'POST /auth/reauthenticate': ok({}) });
    const answers = [reauthRequired(), Response.json({ deleted: true })];
    const s = await setup(() => answers.shift()!);
    await confirmWithEmail(s);
    expect(s.q('delete-account-error')).toBeNull();
    await typeInto(s.q('reauth-password'), 'owner-secret');
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(s.calls().map((c) => c.path)).toEqual(['/api/accounts/profile/delete', '/api/accounts/profile/delete']);
    expect(leave).toHaveBeenCalledWith('/');
  });

  it('keeps any other failure in the dialog', async () => {
    const s = await setup(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    await confirmWithEmail(s);
    expect(s.q('delete-account-error')?.textContent).toContain('We could not reach ERPlora');
    expect(leave).not.toHaveBeenCalled();
  });
});
