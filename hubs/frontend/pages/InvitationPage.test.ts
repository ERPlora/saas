// The invitation (`/invitation` from the email, `/invitations/:id` from a banner; mockups
// `invitation.html`): a centred card with every invitation waiting for the account's answer (the one
// asked for first), each with «Accept and enter» and «Decline»; none (expired, used, another email) →
// «This invitation is no longer valid», with the panel and «Create my own business».
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

import { LIVE_TIMEOUT_MS } from '../../../frontend/live-state';
import { BYE, describeCall, enterView, errorFrame, flush, type MountOptions, mountHubs, subId } from '../__tests__/mount-hubs';
import InvitationPage from './InvitationPage.vue';
import { navigation } from '../open-business';

const invitation = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  hub: { id: `h-${id}`, slug: id, name },
  role: 'hub_manager',
  role_label: 'Manager',
  invited_by: 'Carlos Ruiz',
  invited_at: null,
  expires_at: null,
  message: '',
  ...extra,
});
const ANA = invitation('m1', 'Peluquería Ana');
const NORTE = invitation('m2', 'Bar Norte', { invited_by: 'Pedro Sanz', role: 'hub_employee', role_label: 'Employee' });

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
  document.title = '';
});

async function setup(invitations: unknown[] | null, options: MountOptions = {}) {
  vi.spyOn(navigation, 'assign').mockImplementation(() => undefined);
  const m = await mountHubs(InvitationPage, {
    path: '/invitation',
    api: (call) => {
      const c = describeCall(call);
      if (c.path === '/api/hubs/invitations/accept') return Response.json({ id: 'h-m1', name: 'Peluquería Ana', can_open: true });
      if (c.path === '/api/hubs/businesses/open') return Response.json({ url: 'http://bakery.localhost:8000/auth/login?next=/' });
      return Response.json({});
    },
    ...options,
  });
  const call = await m.live();
  if (invitations) await m.result(call, 'hubs.invitation.list_mine', { invitations });
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const title = () => m.wrapper.get('ion-card-title').text();
  return { ...m, call, testid, title };
}

describe('InvitationPage', () => {
  it('follows the account’s invitations and shows each one with who invites and as what', async () => {
    const s = await setup([ANA]);
    expect(s.client.stream.subscriptions('hubs.invitation.list_mine')).toHaveLength(1);
    expect(s.title()).toBe('You have been invited');
    expect(s.wrapper.get('.shell-lead').text()).toBe('Someone gave you access to their business. Accept to enter.');
    const card = s.testid('invitation-m1');
    expect(card.get('h2').text()).toBe('Peluquería Ana');
    expect(card.get('.invite-by').text()).toBe('Carlos Ruiz invites you · Manager');
    // HUBS-G79: nobody leaves a business by themselves (no such action, as in Square or Toast): the foot says who
    // can take the access away, not a «leave» the panel does not have.
    expect(s.testid('invitation-foot').text()).toBe('The owner or an admin of the business can take this access away.');
    expect(document.title).toBe('You have been invited - ERPlora');
  });

  it('puts the invitation asked for first', async () => {
    const s = await setup([ANA, NORTE], { path: '/invitations/m2', props: { id: 'm2' } });
    expect(s.wrapper.findAll('[data-testid^="invitation-m"]').map((c) => c.get('h2').text())).toEqual(['Bar Norte', 'Peluquería Ana']);
  });

  it('«Accept and enter» accepts and enters the business', async () => {
    const s = await setup([ANA]);
    await s.testid('invitation-m1').get('[data-testid="invitation-accept"]').trigger('click');
    await flush();
    expect(s.calls().map((c) => c.path)).toEqual(['/api/hubs/invitations/accept', '/api/hubs/businesses/open']);
  });

  it('«Decline» asks first', async () => {
    const s = await setup([ANA]);
    await s.testid('invitation-m1').get('[data-testid="invitation-decline"]').trigger('click');
    await flush();
    expect(document.querySelector('[data-testid="decline-dialog"]')?.textContent).toContain('Carlos Ruiz invited you to Peluquería Ana.');
  });

  it('nothing waiting (or not the one asked for): no longer valid, the panel or one’s own business', async () => {
    const s = await setup([NORTE], { path: '/invitations/m9', props: { id: 'm9' } });
    expect(s.title()).toBe('This invitation is no longer valid');
    expect(s.wrapper.get('.shell-lead').text()).toBe('It expired or was already used.');
    expect(s.testid('invitation-expired').text()).toContain('Ask whoever invited you to send it again, to the email you sign in with: laura@example.com.');
    await s.testid('invitation-panel').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/businesses');
    await s.testid('invitation-create-own').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/launch');
  });

  it('loading: a spinner; an error: why, and «Retry»', async () => {
    const s = await setup(null);
    expect(s.testid('invitation-loading').exists()).toBe(true);
    s.call.push(errorFrame(subId(s.client, 'hubs.invitation.list_mine'), 'server_error'));
    await flush();
    expect(s.testid('invitation-error').text()).toContain('We could not load your invitations.');
    expect(s.testid('invitation-retry').exists()).toBe(true);
  });

  it('the stream gone before any answer: an error with «Retry» after the time limit, never a spinner for ever (R-08)', async () => {
    const s = await setup(null);
    s.call.push(BYE);
    await flush();
    expect(s.testid('invitation-loading').exists()).toBe(true);
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.testid('invitation-loading').exists()).toBe(false);
    expect(s.testid('invitation-error').text()).toContain('We could not load your invitations.');
    expect(s.testid('invitation-expired').exists()).toBe(false);
    const streams = s.net.streams.length;
    await s.testid('invitation-retry').trigger('click');
    await s.clock.advance(1);
    expect(s.net.streams.length).toBeGreaterThan(streams);
  });

  it('names the tab again each time it is shown (Ionic reuses the page)', async () => {
    const s = await setup([ANA]);
    document.title = 'Other page';
    enterView(s.wrapper);
    expect(document.title).toBe('You have been invited - ERPlora');
  });

  it('speaks Spanish', async () => {
    const s = await setup([ANA], { locale: 'es' });
    expect(s.title()).toBe('Te han invitado');
    expect(s.testid('invitation-m1').get('.invite-by').text()).toBe('Te invita Carlos Ruiz · Manager');
    expect(s.testid('invitation-m1').get('[data-testid="invitation-accept"]').text()).toContain('Aceptar y entrar');
  });
});
