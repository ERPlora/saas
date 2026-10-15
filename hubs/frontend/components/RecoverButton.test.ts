// «Recover business» wherever a deleted business is listed (audit 2 R-07: the launch card had only «Go to the
// panel»): its owner recovers it within its 90 days (`can.restore`, the server's) with `hubs.business.restore`, and
// the result is said; a refusal (the Free quota taken meanwhile…) says the server's sentence. Anybody else sees
// nothing. In a list the button is named with its business.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { accessibleName, describeCall, flush, ionProps, mountHubs } from '../__tests__/mount-hubs';
import RecoverButton from './RecoverButton.vue';

const DELETED = {
  id: 'plaza',
  name: 'Bar La Plaza',
  can: { open: false, manage: false, restore: true, delete: false },
};

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

const mountIt = (business: Record<string, unknown> = {}, extra: Record<string, unknown> = {}, answer?: () => Response, locale: 'en' | 'es' = 'en') =>
  mountHubs(RecoverButton, {
    props: { business: { ...DELETED, ...business }, ...extra },
    locale,
    api: (call) =>
      describeCall(call).path === '/api/hubs/businesses/restore'
        ? (answer?.() ?? Response.json({ id: 'plaza', name: 'Bar La Plaza', status: 'active' }))
        : Response.json({}),
  });

describe('RecoverButton', () => {
  it('its owner recovers the business, and it is said', async () => {
    const m = await mountIt();
    const button = m.wrapper.get('[data-testid="recover-business"]');
    expect(button.text()).toContain('Recover business');
    await button.trigger('click');
    await flush();
    expect(m.calls().find((c) => c.path === '/api/hubs/businesses/restore')?.body).toEqual({ id: 'plaza' });
    expect(toastSuccess).toHaveBeenCalledWith('Business recovered: Bar La Plaza');
  });

  it('a refusal says the server’s sentence', async () => {
    const m = await mountIt({}, {}, () =>
      Response.json({ error: { code: 'hubs.free_hub_limit', message: 'You already have a free business. Change its plan to create another one.' } }, { status: 409 }),
    );
    await m.wrapper.get('[data-testid="recover-business"]').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('You already have a free business. Change its plan to create another one.');
  });

  it('nothing for whoever may not recover it (not the owner, or its 90 days gone)', async () => {
    const m = await mountIt({ can: { ...DELETED.can, restore: false } });
    expect(m.wrapper.find('ion-button').exists()).toBe(false);
  });

  it('takes the size and the width asked for; in a list, it is named with its business', async () => {
    const m = await mountIt({}, { size: 'large', expand: 'block', named: true }, undefined, 'es');
    const button = m.wrapper.get('[data-testid="recover-business"]');
    expect(ionProps(button, 'size', 'expand')).toEqual({ size: 'large', expand: 'block' });
    expect(button.text()).toContain('Recuperar negocio');
    expect(accessibleName(button)).toBe('Recuperar Bar La Plaza');
  });
});
