// «Create business», the dialog of the businesses page, on its own: the two ways the page opens it (to create a
// business, or to follow one the page has just created), what the page hands it (the account's Free business
// filling its quota, the business being opened) and what it hands back (the business to open).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { flush, ionProps, mountHubs } from '../__tests__/mount-hubs';
import BusinessCreateModal from './BusinessCreateModal.vue';

const DULCE = { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000' };
const READY = { ...DULCE, status: 'active', hub_error: null, can: { open: true } };

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(start: { freeBusiness?: unknown; opening?: string | null } = {}) {
  const freeBusiness = ref(start.freeBusiness ?? null);
  const opening = ref<string | null>(start.opening ?? null);
  const opened = vi.fn();
  const modal = ref<InstanceType<typeof BusinessCreateModal> | null>(null);
  const Host = {
    render: () =>
      h(BusinessCreateModal, {
        ref: modal,
        freeBusiness: freeBusiness.value as never,
        opening: opening.value,
        onOpen: opened,
      }),
  };
  const m = await mountHubs(Host, { path: '/dashboard/businesses', api: () => Response.json({ business_types: [] }) });
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const shown = () => q('create-modal')?.querySelector('.ion-delegate-host') !== null;
  const title = () => q('create-modal')?.querySelector('ion-title')?.textContent;
  /** The page hands over a business just created: the dialog follows it until `hubs.business.get` says it is ready. */
  async function followReady(): Promise<void> {
    modal.value!.onCreated(DULCE, { typeName: null });
    await flush();
    await m.result(await m.live(), 'hubs.business.get', READY);
  }
  return { ...m, modal, opening, opened, q, shown, title, followReady };
}

describe('BusinessCreateModal', () => {
  it('stays closed until the page starts a business, then shows the form', async () => {
    const s = await setup();
    expect(s.shown()).toBe(false);
    s.modal.value!.startCreate();
    await flush();
    expect(s.shown()).toBe(true);
    expect(s.q('create-modal')?.getAttribute('aria-label')).toBe('Create business');
    expect(s.q('create-name') === null).toBe(false);
  });

  it('with the account’s Free business filling its quota, says so instead of the form', async () => {
    const s = await setup({ freeBusiness: { id: 'cafe', slug: 'cafe', name: 'Café Central' } });
    s.modal.value!.startCreate();
    await flush();
    // (booleans: a failing match on an element prints the whole Ionic DOM)
    expect(s.q('create-name') === null).toBe(true);
    expect(s.q('create-free-limit')?.textContent).toContain('You already have a free business');
  });

  it('follows a business the page has just created, and hands it back to the page to open it', async () => {
    const s = await setup();
    s.modal.value!.onCreated(DULCE, { typeName: null });
    await flush();
    expect(s.shown()).toBe(true);
    expect(s.title()).toContain('Preparing Pastelería Dulce');
    await s.result(await s.live(), 'hubs.business.get', READY);
    expect(s.client.stream.subscriptions('hubs.business.get').map((sub) => sub.params)).toEqual([{ id: 'dulce' }]);
    expect(s.title()).toContain('Your business is ready');
    s.q('create-modal-open')!.click();
    await flush();
    expect(s.opened.mock.calls).toEqual([[READY]]);
    expect(s.calls().some((c) => c.path === '/api/hubs/businesses/open')).toBe(false);
  });

  it('«Open business» is off while the page is opening a business', async () => {
    const s = await setup({ opening: 'bakery' });
    await s.followReady();
    expect(ionProps({ element: s.q('create-modal-open')! }, 'disabled')).toEqual({ disabled: true });
    s.opening.value = null;
    await flush();
    expect(ionProps({ element: s.q('create-modal-open')! }, 'disabled')).toEqual({ disabled: false });
  });
});
