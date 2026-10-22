// HUBS-F16 «Change address» (PLAN-SAAS §1.1, round 2026-10-15b): a FormModal for the owner with the new address,
// the host it gives under it, and what follows (the old address stops opening the business but stays the
// business's own). It sends `hubs.business.change_address`; a refusal of the server stays in the dialog, a 422 on
// the field.
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
import AddressDialog from './AddressDialog.vue';

const BUSINESS = { id: 'h1', name: 'Panadería López', slug: 'bakery', host: 'bakery.erplora.com' };
const MOVED = { ...BUSINESS, slug: 'panaderia-lopez', host: 'panaderia-lopez.erplora.com' };

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(api: () => Response = () => Response.json(MOVED)) {
  const open = ref(true);
  const Host = {
    render: () => h(AddressDialog, { business: BUSINESS, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }),
  };
  const m = await mountHubs(Host, { api });
  await flush();
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement & { disabled?: boolean; value?: string };
  async function type(value: string) {
    const input = q('address-dialog-slug');
    input.value = value;
    input.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  return { ...m, open, q, type };
}

describe('AddressDialog', () => {
  it('starts from the current address, says what follows and waits for a different one', async () => {
    const s = await setup();
    const dialog = s.q('address-dialog');
    expect(dialog.getAttribute('aria-label')).toBe('Change the web address of Panadería López');
    expect(s.q('address-dialog-slug').value).toBe('bakery');
    expect(s.q('address-dialog-host').textContent).toBe('bakery.erplora.com');
    expect(dialog.textContent).toContain('Your devices and erplora.com take you to the new address.');
    expect(dialog.textContent).toContain('The old address stops opening the business: links and QR codes with it stop working.');
    expect(dialog.textContent).toContain('Nobody else can take the old address while it is the last one you had.');
    expect(s.q('address-dialog-submit').disabled).toBe(true);
    await s.type('Panaderia-Lopez ');
    expect(s.q('address-dialog-host').textContent).toBe('panaderia-lopez.erplora.com');
    expect(s.q('address-dialog-submit').disabled).toBe(false);
  });

  it('sends the new address in lowercase, says it and closes', async () => {
    const s = await setup();
    await s.type('Panaderia-Lopez');
    s.q('address-dialog-submit').click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([
      ['/api/hubs/businesses/address', { id: 'h1', slug: 'panaderia-lopez' }],
    ]);
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('The business now opens at panaderia-lopez.erplora.com');
    expect(s.open.value).toBe(false);
  });

  it('keeps the dialog with a taken address', async () => {
    const s = await setup(() => apiError(409, 'hubs.slug_taken', 'This address is taken. Choose another one.'));
    await s.type('casa');
    s.q('address-dialog-submit').click();
    await flush();
    expect(s.open.value).toBe(true);
    expect(s.q('address-dialog-error').textContent).toContain('This address is taken. Choose another one.');
  });

  it('puts an address the server refuses on its field', async () => {
    const msg = 'Use only lowercase letters, digits and hyphens, without a hyphen at the start or the end.';
    const s = await setup(() => apiError(422, 'invalid_payload', 'Invalid payload', { slug: msg }));
    await s.type('-casa');
    s.q('address-dialog-submit').click();
    await flush();
    expect((s.q('address-dialog-slug') as HTMLElement & { errorText?: string }).errorText).toBe(msg);
  });
});
