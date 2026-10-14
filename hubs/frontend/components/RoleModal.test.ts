// «Change role» (mockups `business.html` «members-role»): the roles the account may give this member
// (the server's `assignable_roles`), `hubs.member.change_role`, a toast with the new role.
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
import RoleModal from './RoleModal.vue';

const MARTA = member('marta', { name: 'Marta Gil', role: 'hub_manager', role_label: 'Manager', assignable_roles: ['hub_manager', 'hub_employee'] });

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(api: () => Response) {
  const open = ref(true);
  const Host = { render: () => h(RoleModal, { member: MARTA, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }) };
  const m = await mountHubs(Host, { api });
  await flush();
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement & Record<string, unknown>;
  return { ...m, open, q };
}

describe('RoleModal', () => {
  it('offers the roles the server allows, the current one picked', async () => {
    const s = await setup(() => Response.json({}));
    expect(s.q('role-modal').getAttribute('aria-label')).toBe('Change the role of Marta Gil');
    expect(ionProps({ element: s.q('role-select') }, 'value', 'mode', 'fill', 'interface')).toEqual({
      value: 'hub_manager',
      mode: 'md',
      fill: 'outline',
      interface: 'popover',
    });
    expect([...s.q('role-select').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual(['Manager', 'Employee']);
  });

  it('changes it, says the new role, and closes', async () => {
    const s = await setup(() => Response.json({ ...MARTA, role: 'hub_employee', role_label: 'Employee' }));
    s.q('role-select').dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'hub_employee' } }));
    await flush();
    s.q('role-modal-submit').click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/members/change_role', { id: 'marta', role: 'hub_employee' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Marta Gil is now Employee');
    expect(s.open.value).toBe(false);
  });

  it('a lost connection is said in the person’s language', async () => {
    const s = await setup(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    s.q('role-modal-submit').click();
    await flush();
    expect(s.q('role-modal-error').textContent).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('keeps the dialog with a refusal', async () => {
    const s = await setup(() => apiError(403, 'permission_denied', 'You cannot hand out a role equal to or above yours.'));
    s.q('role-modal-submit').click();
    await flush();
    expect(s.q('role-modal-error').textContent).toContain('You cannot hand out a role equal to or above yours.');
    expect(s.open.value).toBe(true);
  });
});
