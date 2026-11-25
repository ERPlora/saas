// The danger card of Account → Profile (mockups `account.html` «profile», «Eliminar tu cuenta»): it says up front
// which businesses hold the account — those it owns (transfer or delete them) and those it pays for (their owner
// enters their own payment details) — named in one line, each linked to its Settings, and keeps «Delete account»
// off meanwhile. The
// server decides in the end (409 with the same businesses, DeleteAccountDialog). Read from `hubs.business.list`, the
// operation the server reads too (`role`: the owner; `is_payer`: it pays for it). While that list is not known
// (loading, failed, or no answer in time) nothing says the account is free to go: deletion stays off, and a failure
// is said with «Retry».
// clock: data only — no code under test compares these dates with now.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));

import { errorFrame, flush, HELLO, ionProps, LIVE_TIMEOUT_MS, mountPanel, profile, subId } from '../__tests__/mount-panel';
import type { BusinessRowOut } from '../../../frontend/sdk-types/hubs';
import DeleteAccountCard from './DeleteAccountCard.vue';

function business(id: string, name: string, overrides: Partial<BusinessRowOut> = {}): BusinessRowOut {
  return {
    id,
    slug: id,
    name,
    host: `${id}.erplora.com`,
    status: 'active',
    status_label: 'Active',
    is_platform: false,
    plan: null,
    role: 'hub_owner',
    role_label: 'Owner',
    last_opened_at: null,
    can_open: true,
    open_blocked_reason: null,
    hub_error: null,
    timezone: 'Europe/Madrid',
    deletion_requested_at: null,
    purge_after: null,
    created_at: '2026-01-01T00:00:00Z',
    can: { open: true, manage: true, restore: false, delete: true },
    unpaid_reason: null,
    unpaid_since: null,
    pay_url: null,
    is_payer: true,
    payer_id: `${id}-payer`,
    ...overrides,
  };
}

const page = (rows: BusinessRowOut[]) => ({ rows, total: rows.length, limit: 100, offset: 0, invitations: [], ownership_offers: [] });

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(rows: BusinessRowOut[]) {
  const s = await mountPanel(DeleteAccountCard, { props: { profile: profile() } });
  const stream = await s.live();
  await s.result(stream, 'hubs.business.list', page(rows));
  return s;
}

describe('DeleteAccountCard', () => {
  it('names the businesses the account owns in one line, each linked to its Settings, and keeps deletion off', async () => {
    const s = await setup([business('b1', 'Panadería López'), business('b2', 'Café Central'), business('b6', 'Bar La Plaza')]);
    expect([...s.q('profile-danger')!.querySelectorAll('.card-text')].map((p) => p.textContent?.trim())).toEqual([
      'You own 3 businesses: transfer or delete them before deleting your account.',
    ]);
    // One line, not a stack of links: the page stays clean.
    expect(s.q('profile-danger-businesses')?.textContent?.trim()).toBe('Panadería López, Café Central, and Bar La Plaza');
    expect(s.q('profile-danger')?.querySelector('ul, li')).toBeNull();
    const links = [...document.querySelectorAll('[data-testid="profile-danger-business"]')];
    expect(links.map((a) => [a.textContent?.trim(), a.getAttribute('href')])).toEqual([
      ['Panadería López', '/dashboard/businesses/b1/settings'],
      ['Café Central', '/dashboard/businesses/b2/settings'],
      ['Bar La Plaza', '/dashboard/businesses/b6/settings'],
    ]);
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: true });
  });

  it('joins the names as the person’s language does', async () => {
    const s = await mountPanel(DeleteAccountCard, { props: { profile: profile() }, locale: 'es' });
    const stream = await s.live();
    await s.result(stream, 'hubs.business.list', page([business('b1', 'Panadería López'), business('b2', 'Café Central')]));
    expect(s.q('profile-danger-businesses')?.textContent?.trim()).toBe('Panadería López y Café Central');
  });

  it('names the businesses it pays for without owning them', async () => {
    const s = await setup([
      business('b3', 'Bar Norte', { role: 'hub_admin', can: { open: true, manage: true, restore: false, delete: false } }),
      // Neither owned nor paid: it holds nobody.
      business('b4', 'Peluquería Ana', { role: 'hub_manager', is_payer: false, can: { open: true, manage: false, restore: false, delete: false } }),
    ]);
    expect(s.q('profile-danger')?.textContent).toContain('You pay for 1 business of other people');
    expect([...document.querySelectorAll('[data-testid="profile-danger-business"]')].map((a) => a.textContent?.trim())).toEqual(['Bar Norte']);
  });

  /** ERPlora's own business, which is only transferred: nobody deletes it, nor pays for it. */
  const platform = () =>
    business('erp', 'ERPlora', {
      is_platform: true,
      is_payer: false,
      payer_id: null,
      can: { open: true, manage: true, restore: false, delete: false },
    });
  const texts = (s: Awaited<ReturnType<typeof setup>>) =>
    [...s.q('profile-danger')!.querySelectorAll('.card-text')].map((p) => p.textContent?.trim());

  it('tells the owner of ERPlora’s own business only to transfer it, in its Members', async () => {
    const s = await setup([platform()]);
    expect(texts(s)).toEqual(["You own ERPlora's business: transfer it before deleting your account."]);
    const link = s.q('profile-danger-business');
    expect([link?.textContent?.trim(), link?.getAttribute('href')]).toEqual(['ERPlora', '/dashboard/businesses/erp/members']);
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: true });
  });

  it('says it in Spanish', async () => {
    const s = await mountPanel(DeleteAccountCard, { props: { profile: profile() }, locale: 'es' });
    await s.result(await s.live(), 'hubs.business.list', page([platform()]));
    expect(texts(s)).toEqual(['Eres propietario del negocio de ERPlora: transfiérelo antes de eliminar tu cuenta.']);
  });

  it('tells the owner of other businesses too what to do with each, counting only those that can be deleted', async () => {
    const s = await setup([business('b1', 'Panadería López'), platform()]);
    expect(texts(s)).toEqual([
      'You own 1 business: transfer or delete it before deleting your account.',
      "You own ERPlora's business: transfer it before deleting your account.",
    ]);
    expect(s.q('profile-danger-businesses')?.textContent?.trim()).toBe('Panadería López and ERPlora');
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: true });
  });

  it('says nothing of ERPlora’s own business to a member who does not own it', async () => {
    const s = await setup([{ ...platform(), role: 'hub_admin' }]);
    expect(texts(s)).toEqual([expect.stringContaining('Your account and what is in it go for good.')]);
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: false });
  });

  it('lets a business in its 90 days of deletion go', async () => {
    const s = await setup([
      business('b5', 'Frutería Sol', { role: 'hub_admin', deletion_requested_at: '2026-10-01T00:00:00Z', can: { open: false, manage: false, restore: false, delete: false } }),
    ]);
    expect(s.q('profile-danger-business')).toBeNull();
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: false });
  });

  it('opens the deletion when nothing holds the account', async () => {
    const s = await setup([]);
    expect(s.q('profile-danger')?.textContent).toContain('Your account and what is in it go for good.');
    s.q('profile-delete')?.click();
    await flush();
    expect(s.q('delete-account')?.querySelector('.ion-delegate-host')).not.toBeNull();
  });

  it('keeps deletion off until it knows which businesses hold the account', async () => {
    const s = await mountPanel(DeleteAccountCard, { props: { profile: profile() } });
    await s.live();
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: true });
    expect(s.q('profile-danger-error')).toBeNull();
  });

  it('says it could not check the businesses, with «Retry», and keeps deletion off when the list fails', async () => {
    const s = await mountPanel(DeleteAccountCard, { props: { profile: profile() } });
    const stream = await s.live();
    stream.push(errorFrame(subId(s.client, 'hubs.business.list'), 'server_error'));
    await flush();
    expect(s.q('profile-danger-error')?.textContent).toContain('We could not check your businesses');
    expect(s.q('profile-danger-error')?.textContent).toContain('You can delete your account once we know which businesses hold it.');
    expect(s.q('profile-danger-retry')?.textContent).toContain('Retry');
    expect(s.q('profile-danger-businesses')).toBeNull();
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: true });
  });

  it('says it could not check the businesses when no answer comes in time', async () => {
    const s = await mountPanel(DeleteAccountCard, { props: { profile: profile() } });
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.q('profile-danger-error')?.textContent).toContain('We could not check your businesses');
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: true });
  });

  it('«Retry» opens the stream again and lets the account go when nothing holds it', async () => {
    const s = await mountPanel(DeleteAccountCard, { props: { profile: profile() } });
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    s.q('profile-danger-retry')?.click();
    await flush();
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.q('profile-danger-error')).toBeNull();
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: true });
    const stream = s.net.lastStream();
    stream.push(HELLO);
    await s.result(stream, 'hubs.business.list', page([]));
    expect(ionProps(s.q('profile-delete'), 'disabled')).toEqual({ disabled: false });
  });
});
