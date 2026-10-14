// «Remove» a member or «Cancel invitation» (mockups `business.html` «members-remove», «cancel-invite»):
// a confirmation that says what follows (they lose access to this business only; the link stops
// working), then `hubs.member.remove` or `hubs.member.cancel`, and a toast.
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

import { flush, mountHubs } from '../__tests__/mount-hubs';
import { member } from '../__tests__/members';
import RemoveDialog from './RemoveDialog.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(row: unknown, api: () => Response = () => Response.json({ id: 'x' })) {
  const open = ref(true);
  const Host = {
    render: () => h(RemoveDialog, { member: row as never, businessName: 'Panadería López', open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }),
  };
  const m = await mountHubs(Host, { api });
  await flush();
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement & Record<string, unknown>;
  return { ...m, open, q };
}

describe('RemoveDialog', () => {
  it('removes a member from this business only', async () => {
    const s = await setup(member('ana', { name: 'Ana Torres' }));
    expect(s.q('remove-dialog').getAttribute('aria-label')).toBe('Remove Ana Torres');
    expect(s.q('remove-dialog').textContent).toContain('Ana Torres loses access to Panadería López at once. Their account and their other businesses stay.');
    expect(s.q('remove-dialog-submit').textContent).toContain('Remove from the business');
    expect(s.q('remove-dialog-submit').color).toBe('danger');
    s.q('remove-dialog-submit').click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/members/remove', { id: 'ana' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Ana Torres was removed from the business');
    expect(s.open.value).toBe(false);
  });

  it('a lost connection is said in the person’s language', async () => {
    const s = await setup(member('ana', { name: 'Ana Torres' }), () => Promise.reject(new TypeError('Failed to fetch')) as never);
    s.q('remove-dialog-submit').click();
    await flush();
    expect(s.q('remove-dialog-error').textContent).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('cancels a pending invitation, with «Back» as the way out', async () => {
    const s = await setup(member('jorge', { email: 'jorge@example.com', status: 'pending', actions: ['change_role', 'resend', 'cancel'] }));
    expect(s.q('remove-dialog').getAttribute('aria-label')).toBe('Cancel the invitation');
    expect(s.q('remove-dialog').textContent).toContain('The invitation to jorge@example.com stops working');
    expect(s.q('remove-dialog-cancel').textContent).toContain('Back');
    s.q('remove-dialog-submit').click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/members/cancel', { id: 'jorge' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Invitation cancelled');
  });
});
