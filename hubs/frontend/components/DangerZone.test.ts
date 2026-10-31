// The Danger zone of a business's Settings (mockups `business.html` «settings»): «Delete business» with
// its 90-day notice, for the owner only (a ConfirmDialog asks for the name); deleted, «Recover
// business» within those days.
// clock: data only — no code under test compares these dates with now.
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

import { apiError, flush, mountHubs } from '../__tests__/mount-hubs';
import DangerZone from './DangerZone.vue';

const BUSINESS = { id: 'h1', name: 'Panadería López', status: 'active', purge_after: null, can: { delete: true, restore: false } };

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

const mountZone = (business: Record<string, unknown>, api: () => Response = () => Response.json({ ...BUSINESS, name: 'Panadería López' })) =>
  mountHubs(DangerZone, { props: { business: { ...BUSINESS, ...business } }, api });

describe('DangerZone', () => {
  it('the owner deletes it, after confirming with the name', async () => {
    const { wrapper } = await mountZone({});
    expect(wrapper.get('h2').text()).toBe('Danger zone');
    expect(wrapper.text()).toContain(
      'It stops working at once. We keep the data for 90 days in case you change your mind.',
    );
    const button = wrapper.get('[data-testid="danger-delete"]');
    expect(button.text()).toContain('Delete business');
    await button.trigger('click');
    await flush();
    expect(document.querySelector('[data-testid="delete-dialog"]')?.getAttribute('aria-label')).toBe('Delete Panadería López');
  });

  it('anybody else reads that only the owner can', async () => {
    const { wrapper } = await mountZone({ can: { delete: false, restore: false } });
    expect(wrapper.find('[data-testid="danger-delete"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('Only the owner can delete the business.');
  });

  it('deleted, the owner recovers it (`can.restore`: a deleted business takes no `delete`) and it says so', async () => {
    const { wrapper, calls } = await mountZone({ status: 'deleting', purge_after: '2027-01-11T10:00:00Z', can: { delete: false, restore: true } });
    expect(wrapper.find('[data-testid="danger-delete"]').exists()).toBe(false);
    await wrapper.get('[data-testid="danger-restore"]').trigger('click');
    await flush();
    expect(calls().map((c) => [c.path, c.body])).toEqual([['/api/hubs/businesses/restore', { id: 'h1' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Business recovered: Panadería López');
  });

  it('deleted and not recoverable by this account, nothing to press', async () => {
    const { wrapper } = await mountZone({ status: 'deleting', can: { delete: false, restore: false } });
    expect(wrapper.find('[data-testid="danger-restore"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="danger-delete"]').exists()).toBe(false);
  });

  it('a recovery the server refuses (erased already) is said', async () => {
    const { wrapper } = await mountZone({ status: 'deleting', can: { delete: false, restore: true } }, () =>
      apiError(409, 'hubs.business_purged', 'This business was erased for good and cannot be recovered.'),
    );
    await wrapper.get('[data-testid="danger-restore"]').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('This business was erased for good and cannot be recovered.');
  });
});
