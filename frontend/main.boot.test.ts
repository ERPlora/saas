// The SaaS SPA entry (mirror of the Hub's): app routes → shell, live client from spa-config, session from the
// `session-me` JSON Django embeds (or GET /api/me), mount only once the router is ready. The SaaS has a login of its
// own: the auth gate sends to the SPA route `/launch`.
import { createMemoryHistory, createRouter, type NavigationFailure, type RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (original) => (await import('./__tests__/main-doubles')).shellDouble(original));
vi.mock('@erplora/ui/components', async (original) => (await import('./__tests__/main-doubles')).componentsDouble(original));
vi.mock('@erplora/ui/sdk', async (original) => (await import('./__tests__/main-doubles')).sdkDouble(original));

import { createShell } from '@erplora/ui/shell';
import { ApiError, createLiveClient, provideLiveClient } from '@erplora/ui/sdk';
import { assistantMessages } from '@erplora/ui/components';

import { fakeShell, importBoot, main, ME, renderShellHtml, setUpMain, shellOptions } from './__tests__/main-boot';
import { sdk } from './__tests__/main-doubles';
import { OPERATION_ROUTES } from './generated/operation-routes';
import entryEn from './locale/en.json';
import entryEs from './locale/es.json';

const page = { template: '<div />' };

setUpMain();

describe('main.ts', () => {
  it('boots on import with the routes Vite globs from <app>/frontend/routes.ts (the launcher, with the sign-in, among them)', () => {
    const routes = importBoot.routes as RouteRecordRaw[];
    expect(routes.find((r) => r.path === '/launch')?.meta?.auth).toBe(false);
  });

  it('collects the routes of every app, in path order, behind a session by default', async () => {
    fakeShell();
    await main.boot({
      '../zeta/frontend/routes.ts': { default: [{ path: '/zeta', component: page }] },
      '../alpha/frontend/routes.ts': {
        default: [
          { path: '/alpha', component: page },
          { path: '/alpha/public', component: page, meta: { auth: false } },
        ],
      },
    });
    const routes = shellOptions().routes as RouteRecordRaw[];
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/alpha', true],
      ['/alpha/public', false],
      ['/zeta', true],
    ]);
  });

  it('feeds the shell every app catalogue, merged per language from <app>/frontend/locale/<lang>.json', async () => {
    fakeShell();
    await main.boot(
      {},
      {
        '../accounts/frontend/locale/en.json': { accounts: { title: 'Sign In' } },
        '../accounts/frontend/locale/es.json': { accounts: { title: 'Iniciar Sesión' } },
        '../zeta/frontend/locale/en.json': { zeta: { title: 'Zeta' } },
      },
    );
    // Plus the entry's own catalogue (frontend/locale), under `saas`, over the shared assistant's words (`assistant`),
    // untouched: the panel's own line under a spent allowance is its configuration's (`spentNoteKey`, below).
    expect(shellOptions().messages).toEqual({
      en: { assistant: assistantMessages.en.assistant, ...entryEn, accounts: { title: 'Sign In' }, zeta: { title: 'Zeta' } },
      es: { assistant: assistantMessages.es.assistant, ...entryEs, accounts: { title: 'Iniciar Sesión' } },
    });
  });

  it('on import, globs the real app catalogues (the login page would show raw keys otherwise)', () => {
    const messages = importBoot.messages as Record<string, { accounts: { login: { title: string } } }>;
    expect([messages.en.accounts.login.title, messages.es.accounts.login.title]).toEqual(['Sign In', 'Iniciar Sesión']);
  });

  it('builds the live client from spa-config with the generated op → route map and provides it to the app', async () => {
    const { app } = fakeShell();
    await main.boot({});
    expect(createLiveClient).toHaveBeenCalledWith(
      expect.objectContaining({ csrfCookieName: 'csrftoken', lang: 'es', googleEnabled: true }),
      { routes: OPERATION_ROUTES },
    );
    expect(provideLiveClient).toHaveBeenCalledWith(sdk.client, app);
  });

  it('feeds the shell the session Django embedded, live at once and without a request', async () => {
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    expect(session.value).toEqual(ME);
    expect(status.value).toBe('live');
    expect(sdk.client.api.call).not.toHaveBeenCalled();
  });

  it("sends a visitor without a session to the SaaS's own sign-in, the launcher of this SPA", async () => {
    fakeShell();
    await main.boot({});
    expect(shellOptions().loginPath).toBe('/launch');
  });

  it('without an embedded session, asks GET /api/me (base.session.me) and goes live with its answer', async () => {
    renderShellHtml(null);
    let answer!: (me: object) => void;
    vi.mocked(sdk.client.api.call).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    fakeShell();
    await main.boot({});
    expect(sdk.client.api.call).toHaveBeenCalledExactlyOnceWith('base.session.me', {});
    const { session, status } = shellOptions();
    expect([session.value, status.value]).toEqual([undefined, 'loading']);
    answer(ME);
    await vi.waitFor(() => expect(status.value).toBe('live'));
    expect(session.value).toEqual(ME);
  });

  it('marks the session as errored when /api/me fails, so the gate stops waiting and sends to the login', async () => {
    renderShellHtml(null);
    vi.mocked(sdk.client.api.call).mockRejectedValue(new ApiError(0, 'network_error', 'Network error'));
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    fakeShell();
    await main.boot({});
    const { session, status } = shellOptions();
    await vi.waitFor(() => expect(status.value).toBe('error'));
    expect(session.value).toBeUndefined();
    expect(logged).toHaveBeenCalledWith('saas: base.session.me failed', expect.any(ApiError));
    logged.mockRestore();
  });

  it('mounts #app only after the router is ready, and after providing the live client', async () => {
    let ready!: () => void;
    const { app } = fakeShell(() => new Promise<void>((resolve) => (ready = resolve)));
    const booted = main.boot({});
    await vi.waitFor(() => expect(createShell).toHaveBeenCalled());
    await Promise.resolve();
    expect(app.mount).not.toHaveBeenCalled();
    ready();
    await booted;
    expect(app.mount).toHaveBeenCalledExactlyOnceWith('#app');
    expect(vi.mocked(provideLiveClient).mock.invocationCallOrder[0]).toBeLessThan(app.mount.mock.invocationCallOrder[0]);
  });

  it('does not mount when the auth gate cancels the first navigation (the page is going to the login)', async () => {
    const gate = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: page }] });
    gate.beforeEach(() => false);
    const cancelled = (await gate.push('/')) as NavigationFailure;
    const { app } = fakeShell(() => Promise.reject(cancelled));
    await expect(main.boot({})).resolves.toBeUndefined();
    expect(app.mount).not.toHaveBeenCalled();
  });

  it('lets any other boot failure surface', async () => {
    fakeShell(() => Promise.reject(new Error('boom')));
    await expect(main.boot({})).rejects.toThrow('boom');
  });
});
