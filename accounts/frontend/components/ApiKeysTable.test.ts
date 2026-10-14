// Account → API keys (mockups `account.html` «keys», README §3b): the live `accounts.apikey.list` in a DataTable —
// name, prefix (`erps_live_…`), permissions (the server's labels), created, last used, «Expires» (W-F14; an
// expired key marked) — with «New key» (NewKeyModal) and «Revoke» on each row, confirmed naming that key
// (W-F8). Empty, it explains what a key is for and offers to create one.
import { DataTable } from '@erplora/ui/components';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  IonModal: (await import('../__tests__/ion-modal-stub')).IonModalStub,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { accessibleName, type ApiCall, errorFrame, flush, keyList, mountPanel, subId } from '../__tests__/mount-panel';
import type { ApiKeyRowOut } from '../../../frontend/sdk-types';
import ApiKeysTable from './ApiKeysTable.vue';

function key(id: string, overrides: Partial<ApiKeyRowOut> = {}): ApiKeyRowOut {
  return {
    id,
    name: 'Contabilidad',
    prefix: 'erps_live_7Kq2abcd',
    scopes: ['billing.read'],
    created_at: '2026-09-03T08:00:00Z',
    last_used_at: '2026-10-13T08:00:00Z',
    expires_at: '2026-12-02T08:00:00Z',
    expired: false,
    ...overrides,
  };
}

const ACCOUNTING = key('k1');
const ZAPIER = key('k2', { name: 'Zapier', prefix: 'erps_live_m9Xaefgh', scopes: ['hubs.read', 'hubs.write'], last_used_at: null, expires_at: null });
const OLD = key('k3', { name: 'Old export', expired: true, expires_at: '2026-09-01T08:00:00Z' });

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(rows: ApiKeyRowOut[] = [ACCOUNTING, ZAPIER], api: (call: ApiCall) => Response | Promise<Response> = () => Response.json(ACCOUNTING)) {
  const s = await mountPanel(ApiKeysTable, { api });
  const stream = await s.live();
  await s.result(stream, 'accounts.apikey.list', keyList(rows));
  return { ...s, stream };
}

describe('ApiKeysTable', () => {
  it('lists the keys with their prefix, permissions, dates and expiry', async () => {
    const s = await setup([ACCOUNTING, ZAPIER, OLD]);
    const text = s.wrapper.text();
    expect(text).toContain('API keys');
    expect(text).toContain('erps_live_7Kq2abcd…');
    expect(text).toContain('Invoices · read');
    expect(text).toContain('Businesses · read, Businesses · write');
    expect(text).toContain('Never');
    expect(s.q('api-key-expired')?.textContent).toContain('Expired');
    expect(text).toContain('3 keys');
  });

  it('fills the page between the topbar and the tabbar: rows scroll inside, toolbar and footer stay', async () => {
    const s = await setup();
    expect((s.wrapper.findComponent(DataTable as unknown as Component).props() as Record<string, unknown>).fill).toBe(true);
  });

  it('opens «New key» with the permissions the server offers', async () => {
    const s = await setup();
    s.q('api-keys-add')?.click();
    await flush();
    expect(s.q('new-key')?.querySelector('.ion-delegate-host')).not.toBeNull();
    expect(s.q('new-key-scope-hubs.write')).not.toBeNull();
  });

  it('paints «Revoke» with its text, and no «rows per page» (the mockup has none)', async () => {
    const s = await setup();
    expect(s.q('api-keys-row-k2-revoke')?.textContent?.trim()).toBe('Revoke');
    expect(accessibleName(s.q('api-keys-row-k2-revoke'))).toBe('Revoke');
    expect(document.querySelector('.data-table__page-size-select')).toBeNull();
  });

  it('revokes a key after a confirmation that names it', async () => {
    const s = await setup();
    s.q('api-keys-row-k2-revoke')?.click();
    await flush();
    expect(s.q('revoke-key')?.getAttribute('aria-label')).toBe('Revoke «Zapier»');
    expect(s.q('revoke-key')?.textContent).toContain('stops working at once');
    s.q('revoke-key-submit')?.click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/api-keys/revoke', { id: 'k2' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Key revoked: «Zapier»');
  });

  it('keeps a refusal of the revocation in its dialog', async () => {
    const s = await setup([ZAPIER], () => Response.json({ error: { code: 'not_found', message: 'That API key does not exist.' } }, { status: 404 }));
    s.q('api-keys-row-k2-revoke')?.click();
    await flush();
    s.q('revoke-key-submit')?.click();
    await flush();
    expect(s.q('revoke-key-error')?.textContent).toContain('That API key does not exist.');
  });

  it('explains an empty list and offers the first key, without the toolbar (mockups «keys-empty»)', async () => {
    const s = await setup([]);
    expect(s.q('api-keys-empty')?.textContent).toContain('You have no keys yet');
    expect(s.q('api-keys-add')).toBeNull();
    s.q('api-keys-empty-new')?.click();
    await flush();
    expect(s.q('new-key')?.querySelector('.ion-delegate-host')).not.toBeNull();
  });

  it('says a failed load with «Retry»', async () => {
    const s = await mountPanel(ApiKeysTable);
    const stream = await s.live();
    stream.push(errorFrame(subId(s.client, 'accounts.apikey.list'), 'server_error'));
    await flush();
    expect(s.q('api-keys-retry')).not.toBeNull();
  });
});
