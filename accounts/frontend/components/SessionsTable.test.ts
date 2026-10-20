// Account → Security, «Active sessions» (mockups `account.html` «security», README §3b): the live
// `accounts.session.list` in a DataTable — device (this session first, marked), browser or app, IP address, last
// use — with «Close session» on every row but this one (an app's asks first: it may be charging at a till, W-F5)
// and «Close other sessions» in the toolbar, confirmed with how many and that the apps close too. A failed load (an
// error, or no answer in time) is said with «Retry», never as «no results · 0 sessions» (audit 2026-10-14, R-04).
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

import { toastError, toastSuccess } from '@erplora/ui/shell';

import {
  accessibleName,
  type ApiCall,
  errorFrame,
  flush,
  HELLO,
  LIVE_TIMEOUT_MS,
  mountPanel,
  session,
  subId,
} from '../__tests__/mount-panel';
import type { SessionListOut, SessionRowOut } from '../../../frontend/sdk-types';
import SessionsTable from './SessionsTable.vue';

const THIS = session(1, { is_current: true, device: 'mac', browser: 'Chrome', browser_version: '130' });
const PHONE = session(2, { device: 'iphone', browser: 'Safari', browser_version: '18', ip: '198.51.100.4' });
const TILL = session(3, { device: 'android', browser: '', browser_version: '', app_version: '4.0', ip: '192.0.2.9' });

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  document.body.innerHTML = '';
});

/** A page of `accounts.session.list` as the server sends it: `total` and `others` count every session, not the page. */
function sessionPage(rows: SessionRowOut[], more: Partial<SessionListOut> = {}): SessionListOut {
  return { rows, total: rows.length, limit: 25, offset: 0, others: rows.filter((row) => !row.is_current).length, ...more };
}

async function setup(rows: SessionRowOut[] = [THIS, PHONE, TILL], api: (call: ApiCall) => Response | Promise<Response> = () => Response.json({ closed: 1 })) {
  const s = await mountPanel(SessionsTable, { api });
  const stream = await s.live();
  await s.result(stream, 'accounts.session.list', sessionPage(rows));
  return { ...s, stream };
}

/** The parameters the live list is followed with now. */
const params = (s: Awaited<ReturnType<typeof mountPanel>>) => s.client.stream.subscriptions('accounts.session.list').map((sub) => sub.params);
const table = (s: Awaited<ReturnType<typeof mountPanel>>) => s.wrapper.findComponent(DataTable as unknown as Component);
/** A row that is not this session, numbered from 10. */
const other = (n: number) => session(10 + n, { last_seen_at: `2026-10-13T08:${String(n % 60).padStart(2, '0')}:00Z` });

const cells = (testid: string) =>
  [...document.querySelectorAll(`[data-testid="${testid}"]`)].map((el) => el.textContent?.replace(/\s+/g, ' ').trim());

describe('SessionsTable', () => {
  it('lists the sessions, this one first and marked, each device and browser named', async () => {
    const s = await setup();
    expect(s.wrapper.text()).toContain('Active sessions');
    expect(cells('session-device')).toEqual(['Mac (macOS)This session', 'iPhone', 'Android']);
    const table = s.wrapper.text();
    expect(table).toContain('Chrome 130');
    expect(table).toContain('Safari 18');
    expect(table).toContain('ERPlora app 4.0');
    expect(table).toContain('198.51.100.4');
    expect(table).toContain('Now');
    // Audit 2 R-25: the browser and the last use are not cut with «…» (DataTable clips a cell's span): they may wrap.
    expect(s.wrapper.findAll('[data-testid="session-browser"]').map((cell) => cell.element.tagName)).toEqual(['DIV', 'DIV', 'DIV']);
    expect(s.wrapper.findAll('[data-testid="session-last-used"]').map((cell) => cell.element.tagName)).toEqual(['DIV', 'DIV', 'DIV']);
  });

  it('offers «Close session», with its text, on every row but this one; no «rows per page»', async () => {
    const s = await setup();
    expect(s.q('sessions-row-1-close')).toBeNull();
    expect(s.q('sessions-row-2-close')?.textContent?.trim()).toBe('Close session');
    expect(accessibleName(s.q('sessions-row-2-close'))).toBe('Close session');
    expect(document.querySelector('.data-table__page-size-select')).toBeNull();
  });

  it('fills the page between the topbar and the tabbar: rows scroll inside, toolbar and footer stay', async () => {
    const s = await setup();
    expect((s.wrapper.findComponent(DataTable as unknown as Component).props() as Record<string, unknown>).fill).toBe(true);
  });

  it('closes a browser’s session at once and says where', async () => {
    const s = await setup();
    s.q('sessions-row-2-close')?.click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/sessions/close', { id: 2 }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Session closed on iPhone');
  });

  it('asks before closing an app’s session: it may be charging at a till', async () => {
    const s = await setup();
    s.q('sessions-row-3-close')?.click();
    await flush();
    expect(s.calls()).toEqual([]);
    expect(s.q('session-close-app')?.getAttribute('aria-label')).toBe('Close the app on Android');
    expect(s.q('session-close-app')?.textContent).toContain('If it is charging at a till');
    s.q('session-close-app-submit')?.click();
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/sessions/close', { id: 3 }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Session closed on Android');
  });

  it('closes the other sessions after saying how many, the apps too', async () => {
    const s = await setup([THIS, PHONE, TILL], () => Response.json({ closed: 2 }));
    s.q('sessions-close-others')?.click();
    await flush();
    expect(s.q('sessions-close-others-dialog')?.textContent).toContain('2 sessions will be closed, also the apps');
    expect(s.q('sessions-close-others-dialog-submit')?.textContent).toContain('Close 2 sessions');
    s.q('sessions-close-others-dialog-submit')?.click();
    await flush();
    expect(s.calls().map((c) => c.path)).toEqual(['/api/accounts/sessions/close_others']);
    expect(toastSuccess).toHaveBeenCalledWith('Sessions closed: 2');
  });

  it('has nothing to close with this session alone', async () => {
    const s = await setup([THIS]);
    expect((s.q('sessions-close-others') as unknown as { disabled: boolean }).disabled).toBe(true);
  });

  it('says a refusal of the close in a toast', async () => {
    const s = await setup([THIS, PHONE], () => Response.json({ error: { code: 'not_found', message: 'That session does not exist or has already ended.' } }, { status: 404 }));
    s.q('sessions-row-2-close')?.click();
    await flush();
    expect(toastError).toHaveBeenCalledWith('That session does not exist or has already ended.');
  });

  it('says a failed load with «Retry»', async () => {
    const s = await mountPanel(SessionsTable);
    const stream = await s.live();
    stream.push(errorFrame(subId(s.client, 'accounts.session.list'), 'server_error'));
    await flush();
    expect(s.q('sessions-retry')).not.toBeNull();
    expect(document.querySelector('.data-table__empty')).toBeNull();
    expect(s.wrapper.text()).not.toContain('0 sessions');
  });

  it('says a failed load, not «no results · 0 sessions» nor a spinner, when no answer comes in time', async () => {
    const s = await mountPanel(SessionsTable);
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.q('sessions-retry')).not.toBeNull();
    expect(s.wrapper.text()).toContain('We could not load your sessions');
    expect(s.wrapper.text()).toContain('We could not reach ERPlora. Check your connection and try again.');
    expect(document.querySelector('.data-table__empty')).toBeNull();
    expect(s.wrapper.text()).not.toContain('0 sessions');
    expect(s.q('sessions-loading')).toBeNull();
  });

  it('«Retry» opens the stream again and lists the sessions when they come', async () => {
    const s = await mountPanel(SessionsTable);
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    s.q('sessions-retry')?.click();
    await flush();
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.q('sessions-retry')).toBeNull();
    expect(s.q('sessions-loading')).not.toBeNull();
    const stream = s.net.lastStream();
    stream.push(HELLO);
    await s.result(stream, 'accounts.session.list', sessionPage([THIS, PHONE]));
    expect(s.q('sessions-loading')).toBeNull();
    expect(cells('session-device')).toEqual(['Mac (macOS)This session', 'iPhone']);
  });
});

// flow: ninguno — FIX accounts (FIX-SAAS-SESSIONS-RESULT-TOO-BIG): with more sessions than one live result carries,
// the list never loaded («The result exceeds 262144 bytes»). The server pages it now; this session stays first.
describe('SessionsTable: more sessions than a page', () => {
  const FIRST_PAGE = [THIS, ...Array.from({ length: 24 }, (_, n) => other(n))];

  async function long(api?: (call: ApiCall) => Response | Promise<Response>) {
    const s = await mountPanel(SessionsTable, { api });
    await s.result(await s.live(), 'accounts.session.list', sessionPage(FIRST_PAGE, { total: 60, others: 59 }));
    return s;
  }

  it('follows one page of the server, 25 rows from the first, and counts every session', async () => {
    const s = await mountPanel(SessionsTable);
    expect(params(s)).toEqual([{ limit: 25, offset: 0 }]);
    await s.result(await s.live(), 'accounts.session.list', sessionPage(FIRST_PAGE, { total: 60, others: 59 }));
    // On a phone, past the 100 rows one page of the server holds, the table pages instead of «Load more».
    expect(table(s).props()).toMatchObject({ serverSide: true, total: 60, page: 0, pageSize: 25, maxWindow: 100 });
    expect(cells('session-device')).toHaveLength(25);
    expect(cells('session-device')[0]).toBe('Mac (macOS)This session');
  });

  it('pages on the server: the next page asks for the next 25 rows', async () => {
    const s = await long();
    s.q('sessions-page-next')?.click();
    await flush();
    expect(params(s)).toEqual([{ limit: 25, offset: 25 }]);
    expect(table(s).props()).toMatchObject({ page: 1 });
  });

  it('«Close other sessions» says how many there are, not only the ones on this page', async () => {
    const s = await long(() => Response.json({ closed: 59 }));
    s.q('sessions-close-others')?.click();
    await flush();
    expect(s.q('sessions-close-others-dialog')?.textContent).toContain('59 sessions will be closed, also the apps');
    s.q('sessions-close-others-dialog-submit')?.click();
    await flush();
    expect(toastSuccess).toHaveBeenCalledWith('Sessions closed: 59');
  });

  it('closes the others from a page without this session, still saying how many there are', async () => {
    const s = await long();
    s.q('sessions-page-next')?.click();
    await flush();
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'accounts.session.list', sessionPage([other(30)], { total: 60, others: 59, offset: 25 }));
    s.q('sessions-close-others')?.click();
    await flush();
    expect(s.q('sessions-close-others-dialog')?.textContent).toContain('59 sessions will be closed, also the apps');
  });

  it('on a phone «Load more» grows one window from the first row, never past the server’s 100 rows', async () => {
    const s = await long();
    table(s).vm.$emit('loadMore');
    await flush();
    expect(params(s)).toEqual([{ limit: 50, offset: 0 }]);
    for (let n = 0; n < 4; n += 1) table(s).vm.$emit('loadMore');
    await flush();
    expect(params(s)).toEqual([{ limit: 100, offset: 0 }]);
  });

  it('a page left empty by sessions closed elsewhere steps back to the last page that has rows', async () => {
    const s = await long();
    s.q('sessions-page-next')?.click();
    await flush();
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'accounts.session.list', sessionPage([], { total: 20, others: 19, offset: 25 }));
    expect(params(s)).toEqual([{ limit: 25, offset: 0 }]);
    expect(document.querySelector('.data-table__empty'), 'never «no sessions» while there are some').toBeNull();
    expect(s.q('sessions-loading')).not.toBeNull();
  });
});
