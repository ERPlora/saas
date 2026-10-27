// «Accept and enter» an invitation (round 17 §2.8): `hubs.invitation.accept`, a success toast, and
// straight into the business when it opens; a business that does not open yet (being prepared,
// suspended) lands on Businesses instead, where it is listed with its reason.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { apiError, describeCall, flush, mountHubs } from './__tests__/mount-hubs';
import { useAcceptInvitation } from './invitations';
import { navigation } from './open-business';

const INVITATION = {
  id: 'm1',
  hub: { id: 'h1', slug: 'ana', name: 'Peluquería Ana' },
  role: 'hub_manager',
  role_label: 'Manager',
  invited_by: 'Carlos Ruiz',
  invited_at: null,
  expires_at: null,
  message: '',
};
const ROW = { id: 'h1', name: 'Peluquería Ana', can_open: true };

let api!: ReturnType<typeof useAcceptInvitation>;
const Probe = defineComponent({
  setup() {
    api = useAcceptInvitation();
    return () => h('div');
  },
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

describe('useAcceptInvitation', () => {
  it('accepts, says so and opens the business', async () => {
    const navigate = vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
    const m = await mountHubs(Probe, {
      api: (call) => {
        const c = describeCall(call);
        if (c.path === '/api/hubs/invitations/accept') return Response.json(ROW);
        return Response.json({ url: 'http://bakery.localhost:8000/auth/login?next=/' });
      },
    });
    const done = api.accept(INVITATION as never);
    expect(api.accepting.value).toBe('m1');
    await done;
    expect(m.calls().map((c) => [c.path, c.body])).toEqual([
      ['/api/hubs/invitations/accept', { id: 'm1' }],
      ['/api/hubs/businesses/open', { id: 'h1', next: '/' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('You now have access to Peluquería Ana');
    expect(navigate).toHaveBeenCalledOnce();
  });

  it('lands on Businesses when the business does not open yet', async () => {
    const m = await mountHubs(Probe, { api: () => Response.json({ ...ROW, can_open: false }) });
    await api.accept(INVITATION as never);
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/dashboard/businesses');
    expect(api.accepting.value).toBeNull();
  });

  it('a lost connection is said in the person’s language', async () => {
    await mountHubs(Probe, { locale: 'es', api: () => Promise.reject(new TypeError('Failed to fetch')) as never });
    await api.accept(INVITATION as never);
    await flush();
    expect(toastError).toHaveBeenCalledWith('No hemos podido conectar con ERPlora. Revisa tu conexión e inténtalo de nuevo.');
  });

  it('says a refusal (expired, already answered) in an error toast', async () => {
    await mountHubs(Probe, { api: () => apiError(404, 'not_found', 'This invitation is no longer valid.') });
    await api.accept(INVITATION as never);
    await flush();
    expect(toastError).toHaveBeenCalledWith('This invitation is no longer valid.');
    expect(api.accepting.value).toBeNull();
  });
});
