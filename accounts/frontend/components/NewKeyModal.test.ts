// «New key» (mockups `account.html` «keys», README §3b and §6.17): a name (required, X-17), the permissions the
// server offers (at least one) and when it expires (30 or 90 days, 90 by default, or never). Creating access asks
// «Confirm it's you» when the server wants it. The whole key is shown once, with «Copy», until «I have saved it».
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

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

import { fakeAllauth, ok } from '../__tests__/allauth-server';
import { type ApiCall, choose, flush, ionProps, mountPanel, reauthRequired, SCOPES, typeInto } from '../__tests__/mount-panel';
import type { ApiKeyRowOut } from '../../../frontend/sdk-types';
import NewKeyModal from './NewKeyModal.vue';

const SECRET = 'erps_live_Rt5wJ3nV8qP2xM6kZ4yH0aB1cD2eF3gH4iJ5kL6mN7oP8qR9';
const ROW: ApiKeyRowOut = {
  id: 'k3',
  name: 'Gestoría Martínez',
  prefix: 'erps_live_Rt5wJ3nV',
  scopes: ['billing.read'],
  created_at: '2026-10-14T08:00:00Z',
  last_used_at: null,
  expires_at: '2027-01-12T08:00:00Z',
  expired: false,
};

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

async function setup(api: (call: ApiCall) => Response | Promise<Response> = () => Response.json({ key: ROW, secret: SECRET }, { status: 201 })) {
  const open = ref(true);
  const Host = { render: () => h(NewKeyModal, { scopes: SCOPES, open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v) }) };
  const s = await mountPanel(Host, { api });
  await flush();
  return { ...s, open };
}

async function fill(s: Awaited<ReturnType<typeof setup>>) {
  await typeInto(s.q('new-key-name'), '  Gestoría Martínez ');
  await choose(s.q('new-key-scope-billing.read'), { checked: true });
}

describe('NewKeyModal', () => {
  it('asks for a name, the permissions the server offers and the expiry, 90 days by default', async () => {
    const s = await setup();
    expect(s.q('new-key')?.getAttribute('aria-label')).toBe('New API key');
    expect(ionProps(s.q('new-key-name'), 'mode', 'fill', 'required')).toEqual({ mode: 'md', fill: 'outline', required: true });
    expect([...document.querySelectorAll('[data-testid^="new-key-scope-"]')].map((el) => el.textContent?.trim())).toEqual([
      'Businesses · read',
      'Businesses · write',
      'Invoices · read',
    ]);
    expect(ionProps(s.q('new-key-expiry'), 'value', 'mode', 'fill', 'interface')).toEqual({
      value: '90',
      mode: 'md',
      fill: 'outline',
      interface: 'popover',
    });
    expect([...s.q('new-key-expiry')!.querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'In 30 days',
      'In 90 days',
      'Never',
    ]);
    expect(s.q('new-key')?.textContent).toContain('You will see the whole key only once');
  });

  it('waits for a name and at least one permission (X-17)', async () => {
    const s = await setup();
    expect(ionProps(s.q('new-key-submit'), 'disabled')).toEqual({ disabled: true });
    await typeInto(s.q('new-key-name'), '   ');
    await choose(s.q('new-key-scope-hubs.read'), { checked: true });
    expect(ionProps(s.q('new-key-submit'), 'disabled')).toEqual({ disabled: true });
    await typeInto(s.q('new-key-name'), 'Zapier');
    expect(ionProps(s.q('new-key-submit'), 'disabled')).toEqual({ disabled: false });
    await choose(s.q('new-key-scope-hubs.read'), { checked: false });
    expect(ionProps(s.q('new-key-submit'), 'disabled')).toEqual({ disabled: true });
  });

  it('creates the key and shows it whole, once, with «Copy», until «I have saved it»', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    const s = await setup();
    await fill(s);
    await choose(s.q('new-key-expiry'), { value: 'never' });
    s.q('new-key-submit')?.click();
    await flush();
    expect(s.calls().map((c) => [c.method, c.path, c.body])).toEqual([
      ['POST', '/api/accounts/api-keys', { name: 'Gestoría Martínez', scopes: ['billing.read'], expires_in_days: null }],
    ]);
    // No toast while the key is on screen: on a phone it would cover the key, shown this once (ACCOUNTS-F31).
    expect(toastSuccess).not.toHaveBeenCalledWith('Key created: «Gestoría Martínez»');
    expect(s.q('new-key-secret')?.textContent).toContain(SECRET);
    expect(s.q('new-key')?.textContent).toContain('you will not see it again');
    expect(s.q('new-key')?.getAttribute('data-backdrop-dismiss')).toBe('false');
    s.q('new-key-copy')?.click();
    await flush();
    expect(writeText).toHaveBeenCalledWith(SECRET);
    expect(toastSuccess).toHaveBeenCalledWith('Key copied');
    s.q('new-key-done')?.click();
    await flush();
    expect(s.open.value).toBe(false);
    expect(toastSuccess).toHaveBeenCalledWith('Key created: «Gestoría Martínez»');
  });

  it('says the key was created when the sheet is closed by its ✕ too, and says nothing when no key was made', async () => {
    const s = await setup();
    await fill(s);
    s.q('new-key-submit')?.click();
    await flush();
    s.open.value = false;
    await flush();
    expect(toastSuccess).toHaveBeenCalledExactlyOnceWith('Key created: «Gestoría Martínez»');

    vi.mocked(toastSuccess).mockClear();
    s.open.value = true;
    await flush();
    s.open.value = false;
    await flush();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('sends the expiry chosen', async () => {
    const s = await setup();
    await fill(s);
    await choose(s.q('new-key-expiry'), { value: '30' });
    s.q('new-key-submit')?.click();
    await flush();
    expect(s.calls()[0].body).toMatchObject({ expires_in_days: 30 });
  });

  it('asks «Confirm it’s you» by password when the server wants it, then creates the key', async () => {
    const server = fakeAllauth({ 'POST /auth/reauthenticate': ok({}) });
    const answers = [reauthRequired(), Response.json({ key: ROW, secret: SECRET }, { status: 201 })];
    const s = await setup(() => answers.shift()!);
    await fill(s);
    s.q('new-key-submit')?.click();
    await flush();
    expect(s.q('new-key-error')).toBeNull();
    await typeInto(s.q('reauth-password'), 'owner-secret');
    s.q('reauth-modal-submit')?.click();
    await flush();
    expect(server.callsTo('POST /auth/reauthenticate')).toHaveLength(1);
    expect(s.calls().map((c) => c.path)).toEqual(['/api/accounts/api-keys', '/api/accounts/api-keys']);
    expect(s.q('new-key-secret')?.textContent).toContain(SECRET);
  });

  it('keeps the form when the confirmation is closed', async () => {
    const s = await setup(() => reauthRequired());
    await fill(s);
    s.q('new-key-submit')?.click();
    await flush();
    s.q('reauth-modal-cancel')?.click();
    await flush();
    expect(s.q('new-key-secret')).toBeNull();
    expect(ionProps(s.q('new-key-name'), 'value')).toEqual({ value: '  Gestoría Martínez ' });
    expect(s.open.value).toBe(true);
  });

  it('keeps a refusal in the dialog (the ceiling of keys)', async () => {
    const s = await setup(() =>
      Response.json({ error: { code: 'accounts.api_key_limit', message: 'You already have 50 API keys: revoke one you no longer use.' } }, { status: 409 }),
    );
    await fill(s);
    s.q('new-key-submit')?.click();
    await flush();
    expect(s.q('new-key-error')?.textContent).toContain('You already have 50 API keys');
  });
});
