// «Create business», the dialog of the businesses page, on its own: what the page hands it (whether it is open, the
// business it follows and that business as `hubs.business.get` says it is now, the account's Free business filling
// its quota, the business being opened) and what it hands back (open or closed, the business its own form created,
// the business to open).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, reactive } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (original) => (await import('../__tests__/module-mocks')).shellWithToastSpies(original));

import { describeCall, flush, ionProps, mountHubs } from '../__tests__/mount-hubs';
import { iconAction, labelled } from '../../../frontend/__tests__/icon-action';
import BusinessCreateModal from './BusinessCreateModal.vue';

const DULCE = { id: 'dulce', name: 'Pastelería Dulce', host: 'dulce.localhost:8000' };
const FOLLOWED = { ...DULCE, typeName: null };
const READY = { ...DULCE, status: 'active', hub_error: null, can: { open: true } };

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(start: Record<string, unknown> = {}) {
  const props = reactive<Record<string, unknown>>({ open: false, created: null, createdNow: undefined, freeBusiness: null, opening: null, ...start });
  const handed = { open: vi.fn(), created: vi.fn(), closed: vi.fn() };
  const Host = {
    render: () =>
      h(BusinessCreateModal, {
        ...props,
        'onUpdate:open': (value: boolean) => {
          props.open = value;
          if (!value) handed.closed();
        },
        onCreated: handed.created,
        onOpen: handed.open,
      } as never),
  };
  const m = await mountHubs(Host, {
    path: '/dashboard/businesses',
    api: (call) => {
      const c = describeCall(call);
      if (c.path === '/api/hubs/businesses' && c.method === 'POST') return Response.json({ ...DULCE, status: 'preparing' });
      return Response.json({ business_types: [] });
    },
  });
  await flush();
  const q = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const shown = () => q('create-modal')?.querySelector('.ion-delegate-host') !== null;
  const title = () => q('create-modal')?.querySelector('ion-title')?.textContent;
  return { ...m, props, handed, q, shown, title };
}

describe('BusinessCreateModal', () => {
  it('stays closed until the page opens it, then shows the form', async () => {
    const s = await setup();
    expect(s.shown()).toBe(false);
    s.props.open = true;
    await flush();
    expect(s.shown()).toBe(true);
    expect(s.q('create-modal')?.getAttribute('aria-label')).toBe('Create business');
    expect(s.q('create-name') === null).toBe(false);
  });

  it('with the account’s Free business filling its quota, says so instead of the form', async () => {
    const s = await setup({ open: true, freeBusiness: { id: 'cafe', slug: 'cafe', name: 'Café Central' } });
    // (booleans: a failing match on an element prints the whole Ionic DOM)
    expect(s.q('create-name') === null).toBe(true);
    expect(s.q('create-free-limit')?.textContent).toContain('You already have a free business');
  });

  it('hands the page the business its own form created', async () => {
    const s = await setup({ open: true });
    const name = s.q('create-name') as HTMLElement & { value?: string };
    name.value = DULCE.name;
    name.dispatchEvent(new CustomEvent('ionInput', { detail: { value: DULCE.name } }));
    await flush();
    s.q('create-modal-submit')!.click();
    await flush();
    expect(s.handed.created).toHaveBeenCalledTimes(1);
    expect(s.handed.created.mock.calls[0][0]).toMatchObject(DULCE);
    expect(s.handed.created.mock.calls[0][1]).toEqual({ typeName: null });
  });

  it('follows the business the page hands it, «Preparing» then «ready», and hands it back to open it', async () => {
    const s = await setup({ open: true, created: FOLLOWED });
    expect(s.title()).toContain('Preparing Pastelería Dulce');
    s.props.createdNow = READY;
    await flush();
    expect(s.title()).toContain('Your business is ready');
    s.q('create-modal-open')!.click();
    await flush();
    expect(s.handed.open.mock.calls).toEqual([[READY]]);
    expect(s.calls().some((c) => c.path === '/api/hubs/businesses/open')).toBe(false);
  });

  it('«Open business» is off while the page is opening a business', async () => {
    const s = await setup({ open: true, created: FOLLOWED, createdNow: READY, opening: 'bakery' });
    expect(iconAction(s.q('create-modal-open'))).toEqual(labelled('Open business'));
    expect(ionProps({ element: s.q('create-modal-open')! }, 'disabled')).toEqual({ disabled: true });
    s.props.opening = null;
    await flush();
    expect(ionProps({ element: s.q('create-modal-open')! }, 'disabled')).toEqual({ disabled: false });
  });

  it('closing it from a step tells the page it is closed', async () => {
    const s = await setup({ open: true, created: FOLLOWED });
    s.q('create-modal-close-list')!.click();
    await flush();
    expect(s.handed.closed).toHaveBeenCalledTimes(1);
    expect(s.shown()).toBe(false);
  });
});
