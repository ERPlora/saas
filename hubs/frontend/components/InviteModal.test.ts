// «Invite» (mockups `business.html` «members-invite»): a dialog with the email, the role (only those the
// account may hand out) and an optional message; `hubs.member.invite`, a toast naming who was invited.
// With every place of the plan taken it says so and does not send.
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

import { apiError, flush, ionProps, mountHubs } from '../__tests__/mount-hubs';
import { member } from '../__tests__/members';
import InviteModal from './InviteModal.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(api: () => Response, extra: Record<string, unknown> = {}) {
  const open = ref(true);
  const Host = {
    render: () =>
      h(InviteModal, {
        business: { id: 'h1', name: 'Panadería López' },
        invitableRoles: ['hub_admin', 'hub_manager', 'hub_employee'],
        seats: { used: 2, limit: 3 },
        ...extra,
        open: open.value,
        'onUpdate:open': (v: boolean) => (open.value = v),
      }),
  };
  const m = await mountHubs(Host, { api });
  await flush();
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement & Record<string, unknown>;
  async function fire(id: string, event: string, value: string) {
    q(id).dispatchEvent(new CustomEvent(event, { detail: { value } }));
    await flush();
  }
  return { ...m, open, q, fire };
}

describe('InviteModal', () => {
  it('asks the email, the role among those one may hand out (employee first picked) and a message', async () => {
    const s = await setup(() => Response.json(member('jorge')));
    expect(s.q('invite-modal').getAttribute('aria-label')).toBe('Invite to Panadería López');
    expect(ionProps({ element: s.q('invite-email') }, 'type', 'mode', 'fill', 'label')).toEqual({ type: 'email', mode: 'md', fill: 'outline', label: 'Email' });
    expect(ionProps({ element: s.q('invite-role') }, 'value')).toEqual({ value: 'hub_employee' });
    expect([...s.q('invite-role').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual(['Admin', 'Manager', 'Employee']);
    expect(ionProps({ element: s.q('invite-message') }, 'mode', 'fill')).toEqual({ mode: 'md', fill: 'outline' });
    expect(s.q('invite-modal').textContent).toContain('We send an email with the link. The invitation lasts 7 days.');
    expect(s.q('invite-seats').textContent).toBe('2 of 3 places on the plan');
  });

  it('sends the invitation, says to whom, and closes', async () => {
    const s = await setup(() => Response.json(member('jorge', { email: 'jorge@example.com' })));
    await s.fire('invite-email', 'ionInput', 'jorge@example.com');
    await s.fire('invite-role', 'ionChange', 'hub_manager');
    await s.fire('invite-message', 'ionInput', 'Welcome');
    s.q('invite-modal-submit').click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([
      ['/api/hubs/members/invite', { hub_id: 'h1', email: 'jorge@example.com', role: 'hub_manager', message: 'Welcome' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Invitation sent to jorge@example.com');
    expect(s.open.value).toBe(false);
  });

  it('puts an invalid email on its field and keeps the dialog', async () => {
    const s = await setup(() => apiError(422, 'invalid_payload', 'Invalid payload', { email: 'Enter a valid email address.' }));
    await s.fire('invite-email', 'ionInput', 'nope');
    s.q('invite-modal-submit').click();
    await flush();
    expect(ionProps({ element: s.q('invite-email') }, 'errorText')).toEqual({ errorText: 'Enter a valid email address.' });
    expect(s.open.value).toBe(true);
  });

  it('says the server’s seat limit as it says it', async () => {
    const s = await setup(() => apiError(409, 'hubs.seat_limit', 'This plan covers 3 people and they are all taken.'));
    await s.fire('invite-email', 'ionInput', 'a@example.com');
    s.q('invite-modal-submit').click();
    await flush();
    expect(s.q('invite-modal-error').textContent).toContain('This plan covers 3 people and they are all taken.');
  });

  it('when the server says every place is taken, it says so and stops sending', async () => {
    const s = await setup(() => apiError(409, 'hubs.seat_limit', 'This plan covers 3 people and they are all taken.'));
    await s.fire('invite-email', 'ionInput', 'a@example.com');
    s.q('invite-modal-submit').click();
    await flush();
    expect(s.q('invite-full').textContent).toContain('The plan has no free places left');
    expect(s.q('invite-modal-submit').disabled).toBe(true);
  });

  it('a lost connection is said in the person’s language', async () => {
    const s = await setup(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    await s.fire('invite-email', 'ionInput', 'a@example.com');
    s.q('invite-modal-submit').click();
    await flush();
    expect(s.q('invite-modal-error').textContent).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('with every place taken, says so and does not send', async () => {
    const s = await setup(() => Response.json({}), { seats: { used: 3, limit: 3 } });
    expect(s.q('invite-full').textContent).toContain('The plan has no free places left');
    expect(s.q('invite-modal-submit').disabled).toBe(true);
  });
});
