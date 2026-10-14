// «Decline» an invitation (README §5, U-06): a confirmation that names who invited and to what, with
// «Cancel» as the safe choice; declining runs `hubs.invitation.decline` (the row goes) and says so.
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

import { apiError, flush, mountHubs } from '../__tests__/mount-hubs';
import DeclineDialog from './DeclineDialog.vue';

const INVITATION = {
  id: 'm1',
  hub: { id: 'h1', slug: 'ana', name: 'Peluquería Ana' },
  role: 'hub_manager',
  role_label: 'Manager',
  invited_by: 'Carlos Ruiz',
  invited_at: null,
  expires_at: null,
  message: '',
};

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(api: () => Response, invitation: unknown = INVITATION, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const declined = vi.fn();
  const Host = {
    render: () =>
      h(DeclineDialog, {
        invitation: invitation as never,
        open: open.value,
        'onUpdate:open': (value: boolean) => (open.value = value),
        onDeclined: declined,
      }),
  };
  const m = await mountHubs(Host, { api, locale });
  await flush();
  const dialog = () => document.querySelector('[data-testid="decline-dialog"]') as HTMLElement;
  return { ...m, open, declined, dialog };
}

describe('DeclineDialog', () => {
  it('names the business and who invited, with Decline in red', async () => {
    const s = await setup(() => Response.json({ id: 'm1' }));
    expect(s.dialog().getAttribute('aria-label')).toBe('Decline the invitation');
    expect(s.dialog().textContent).toContain('Carlos Ruiz invited you to Peluquería Ana. If you decline it, they will have to invite you again.');
    const confirm = document.querySelector('[data-testid="decline-dialog-submit"]') as HTMLElement & { color?: string };
    expect(confirm.textContent).toContain('Decline');
    expect(confirm.color).toBe('danger');
  });

  it('without an inviter, still says what is declined', async () => {
    const s = await setup(() => Response.json({ id: 'm1' }), { ...INVITATION, invited_by: null }, 'es');
    expect(s.dialog().textContent).toContain('Te invitaron a Peluquería Ana. Si la rechazas, tendrán que invitarte otra vez.');
  });

  it('declines, says so, closes and tells the page', async () => {
    const s = await setup(() => Response.json({ id: 'm1' }));
    (document.querySelector('[data-testid="decline-dialog-submit"]') as HTMLElement).click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/invitations/decline', { id: 'm1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Invitation declined');
    expect(s.open.value).toBe(false);
    expect(s.declined).toHaveBeenCalledOnce();
  });

  it('a lost connection is said in the person’s language', async () => {
    await setup(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    (document.querySelector('[data-testid="decline-dialog-submit"]') as HTMLElement).click();
    await flush();
    expect(document.querySelector('[data-testid="decline-dialog-error"]')?.textContent).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('keeps the dialog open with the error when the server refuses', async () => {
    const s = await setup(() => apiError(404, 'not_found', 'This invitation is no longer valid.'));
    (document.querySelector('[data-testid="decline-dialog-submit"]') as HTMLElement).click();
    await flush();
    expect(s.open.value).toBe(true);
    expect(document.querySelector('[data-testid="decline-dialog-error"]')?.textContent).toContain('This invitation is no longer valid.');
    expect(s.declined).not.toHaveBeenCalled();
  });
});
