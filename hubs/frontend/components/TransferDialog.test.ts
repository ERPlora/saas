// «Transfer ownership»: delicate, so the
// name of the business is typed to confirm; `hubs.ownership.transfer` offers the business to that
// member (7 days to accept) and says so.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { toastSuccess } from '@erplora/ui/shell';

import { flush, mountHubs } from '../__tests__/mount-hubs';
import { member } from '../__tests__/members';
import TransferDialog from './TransferDialog.vue';

const CARLOS = member('carlos', { name: 'Carlos Ruiz', email: 'carlos@example.com', role: 'hub_admin', actions: ['change_role', 'remove', 'transfer'] });

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function mountTransfer(api: () => Response, business: { name?: string; is_platform?: boolean } = {}) {
  const open = ref(true);
  const Host = {
    render: () =>
      h(TransferDialog, { member: CARLOS, business: { id: 'h1', name: 'Panadería López', is_platform: false, ...business }, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }),
  };
  const m = await mountHubs(Host, { api });
  await flush();
  return { ...m, open, q: (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement & Record<string, unknown> };
}

describe('TransferDialog', () => {
  it('a lost connection is said in the person’s language', async () => {
    const s = await mountTransfer(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    s.q('transfer-dialog-input').dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Panadería López' } }));
    await flush();
    s.q('transfer-dialog-submit').click();
    await flush();
    expect(s.q('transfer-dialog-error').textContent).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('asks for the business’s name, offers the ownership and says to whom', async () => {
    const { q, open, ...m } = await mountTransfer(() => Response.json({ id: 't1', to_email: 'carlos@example.com', status: 'pending' }));
    expect(q('transfer-dialog').getAttribute('aria-label')).toBe('Transfer Panadería López');
    expect(q('transfer-dialog').textContent).toContain('We offer the ownership to Carlos Ruiz.');
    expect(q('transfer-dialog').textContent).toContain('They have 7 days to accept it; until then nothing changes.');
    // HUBS-F28: a paid plan goes with the business until its paid period ends; the card does not.
    expect(q('transfer-dialog').textContent).toContain(
      'A paid plan stays until the end of the period already paid; then the new owner pays it with their card, and the current one is not charged again.',
    );
    expect(q('transfer-dialog-submit').disabled).toBe(true);
    q('transfer-dialog-input').dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Panadería López' } }));
    await flush();
    q('transfer-dialog-submit').click();
    await flush();
    expect(m.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/ownership/transfer', { hub_id: 'h1', member_id: 'carlos' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Offer sent to carlos@example.com: they have 7 days to accept it');
    expect(open.value).toBe(false);
  });

  it('says nothing of a plan when it hands ERPlora’s own business over', async () => {
    const s = await mountTransfer(() => Response.json({}), { name: 'ERPlora', is_platform: true });
    const dialog = s.q('transfer-dialog');
    expect(dialog.textContent).toContain('They have 7 days to accept it; until then nothing changes.');
    expect(dialog.textContent).not.toMatch(/plan|card|charged/i);
  });
});
