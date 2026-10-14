// «Delete business» (PLAN-SAAS §3.4, round 17 §2.11; mockups `business.html` «settings-delete»): a
// ConfirmDialog that asks to type the business's name, says what follows (stops at once, 90 days to
// recover it, the plan back to Free, an email with the data), runs `hubs.business.delete` with the
// name typed and says until when it can be recovered.
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
import DeleteDialog from './DeleteDialog.vue';

const BUSINESS = { id: 'h1', name: 'Panadería López' };
const DELETED = { ...BUSINESS, status: 'deleting', purge_after: '2027-01-11T10:00:00Z' };

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(api: () => Response) {
  const open = ref(true);
  const deleted = vi.fn();
  const Host = {
    render: () =>
      h(DeleteDialog, { business: BUSINESS, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), onDeleted: deleted }),
  };
  const m = await mountHubs(Host, { api });
  await flush();
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement & { disabled?: boolean; color?: string };
  async function typeName(value: string) {
    const input = q('delete-dialog-input');
    (input as HTMLElement & { value?: string }).value = value;
    input.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  return { ...m, open, deleted, q, typeName };
}

describe('DeleteDialog', () => {
  it('names the business, says what follows, and waits for its name', async () => {
    const s = await setup(() => Response.json(DELETED));
    const dialog = s.q('delete-dialog');
    expect(dialog.getAttribute('aria-label')).toBe('Delete Panadería López');
    expect(dialog.textContent).toContain('It stops working right now for everyone. You can recover it for 90 days; after that it is erased for good.');
    expect(dialog.textContent).toContain('Its plan is cancelled now: if you recover it, it comes back on Free.');
    expect(dialog.textContent).toContain('We send you an email with a link to download its data.');
    expect(s.q('delete-dialog-submit').color).toBe('danger');
    expect(s.q('delete-dialog-submit').disabled).toBe(true);
    await s.typeName('panadería lópez');
    expect(s.q('delete-dialog-submit').disabled).toBe(false);
  });

  it('deletes with the name typed, says until when it can be recovered, closes and tells the page', async () => {
    const s = await setup(() => Response.json(DELETED));
    await s.typeName('Panadería López');
    s.q('delete-dialog-submit').click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/businesses/delete', { id: 'h1', confirm_name: 'Panadería López' }]]);
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toMatch(/^Business deleted: Panadería López\. You can recover it until Jan 11, 2027/);
    expect(s.open.value).toBe(false);
    expect(s.deleted).toHaveBeenCalledWith(DELETED);
  });

  it('a lost connection is said in the person’s language', async () => {
    const s = await setup(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    await s.typeName('Panadería López');
    s.q('delete-dialog-submit').click();
    await flush();
    expect(s.q('delete-dialog-error').textContent).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('keeps the dialog with the server’s refusal', async () => {
    const s = await setup(() => apiError(403, 'permission_denied', 'Your role in this business does not allow it.'));
    await s.typeName('Panadería López');
    s.q('delete-dialog-submit').click();
    await flush();
    expect(s.open.value).toBe(true);
    expect(s.q('delete-dialog-error').textContent).toContain('Your role in this business does not allow it.');
  });
});
