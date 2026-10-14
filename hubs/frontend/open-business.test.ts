// «Open»: `hubs.business.open` checks the member and the business and answers where the jump starts —
// the Hub's `/auth/login?next=`, which binds the jump to this browser with a `state` of its own — and
// the page goes there (a top-level navigation; no code ever passes through the SPA). A refusal (being
// prepared, suspended, deleted) is said in an error toast, in the person's language when it is not the
// server's, and nothing leaves the page.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError } from '@erplora/ui/shell';

import { apiError, flush, mountHubs } from './__tests__/mount-hubs';
import { navigation, useOpenBusiness } from './open-business';

const START = 'http://bakery.localhost:8000/auth/login?next=/';

let api!: ReturnType<typeof useOpenBusiness>;
const Probe = defineComponent({
  setup() {
    api = useOpenBusiness();
    return () => h('div');
  },
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

describe('useOpenBusiness', () => {
  it('asks where the jump starts (next = its home by default) and goes there, posting nothing itself', async () => {
    const assign = vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit');
    const m = await mountHubs(Probe, { api: () => Response.json({ url: START }) });
    const done = api.open({ id: 'h1', name: 'Bakery' });
    expect(api.opening.value).toBe('h1');
    expect(await done).toBe(true);
    expect(m.calls()).toEqual([
      expect.objectContaining({ method: 'POST', path: '/api/hubs/businesses/open', body: { id: 'h1', next: '/' } }),
    ]);
    expect(assign).toHaveBeenCalledWith(START);
    expect(submit).not.toHaveBeenCalled();
    expect(document.querySelector('form')).toBeNull();
    // The page is leaving: it stays «opening» until it does.
    expect(api.opening.value).toBe('h1');
  });

  it('opens at a path of the business when asked', async () => {
    vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
    const m = await mountHubs(Probe, { api: () => Response.json({ url: 'http://bakery.localhost:8000/auth/login?next=/apps' }) });
    await api.open({ id: 'h1', name: 'Bakery' }, '/apps');
    expect(m.calls()[0].body).toEqual({ id: 'h1', next: '/apps' });
  });

  it('a lost connection is said in the person’s language, not the SDK’s', async () => {
    const assign = vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
    await mountHubs(Probe, { locale: 'es', api: () => Promise.reject(new TypeError('Failed to fetch')) as never });
    expect(await api.open({ id: 'h1', name: 'Bakery' })).toBe(false);
    await flush();
    expect(toastError).toHaveBeenCalledWith('No hemos podido conectar con ERPlora. Revisa tu conexión e inténtalo de nuevo.');
    expect(assign).not.toHaveBeenCalled();
  });

  it('back from the Hub with the browser’s back button (a page from the cache), nothing is opening any more', async () => {
    vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
    await mountHubs(Probe, { api: () => Response.json({ url: START }) });
    await api.open({ id: 'h1', name: 'Bakery' });
    expect(api.opening.value).toBe('h1');
    window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: false }));
    expect(api.opening.value).toBe('h1');
    window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    expect(api.opening.value).toBeNull();
  });

  it('says a refusal in an error toast and leaves nothing pending', async () => {
    const assign = vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
    await mountHubs(Probe, {
      api: () => apiError(409, 'hubs.business_suspended', 'This business is suspended until its payment is settled.'),
    });
    expect(await api.open({ id: 'h1', name: 'Bakery' })).toBe(false);
    await flush();
    expect(toastError).toHaveBeenCalledWith('This business is suspended until its payment is settled.');
    expect(api.opening.value).toBeNull();
    expect(assign).not.toHaveBeenCalled();
  });
});
