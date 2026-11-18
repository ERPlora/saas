// The panel's action center: the shell paints the bell, the card of a new notice and the panel; the panel hands it
// where its notices come from, the unpaid invoices of the account's businesses.
import { expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createShell: vi.fn(),
}));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  createLiveClient: vi.fn(() => ({ api: { call: vi.fn() } })),
  createAllauthClient: vi.fn(() => ({})),
  provideLiveClient: vi.fn(),
}));

import { createShell } from '@erplora/ui/shell';

import { useUnpaidNotices } from '../billing/frontend/notices';

const ME = { user: { id: 'u1', label: 'Ana' }, permissions: [], menu: [], apps: [], language: 'en', preferences: null, account_language: null };

it('hands the shell the unpaid invoices as the source of its notices', async () => {
  document.body.innerHTML = `
    <script id="spa-config" type="application/json">${JSON.stringify({ csrfCookieName: 'csrftoken', lang: 'en' })}</script>
    <script id="session-me" type="application/json">${JSON.stringify(ME)}</script>
    <div id="app"></div>`;
  vi.mocked(createShell).mockResolvedValue({ app: { mount: vi.fn() }, router: { isReady: () => Promise.resolve() } } as never);
  await import('./main');
  await vi.waitFor(() => expect(createShell).toHaveBeenCalledOnce());
  expect(vi.mocked(createShell).mock.calls[0][0].actionNotices).toBe(useUnpaidNotices);
});
