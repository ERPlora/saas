// The accounts `routes.ts`: routes → pages and nothing else (main.ts reads the default export).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine.
vi.mock('./pages/LoginErrorPage.vue', () => ({ default: { name: 'LoginErrorPage' } }));
vi.mock('./pages/VerifyEmailPage.vue', () => ({ default: { name: 'VerifyEmailPage' } }));
vi.mock('./pages/PasswordResetPage.vue', () => ({ default: { name: 'PasswordResetPage' } }));
vi.mock('./pages/PasswordResetKeyPage.vue', () => ({ default: { name: 'PasswordResetKeyPage' } }));
vi.mock('./pages/TwoFactorAuthenticatePage.vue', () => ({ default: { name: 'TwoFactorAuthenticatePage' } }));
vi.mock('./pages/TwoFactorSettingsPage.vue', () => ({ default: { name: 'TwoFactorSettingsPage' } }));
vi.mock('./pages/ReauthenticatePage.vue', () => ({ default: { name: 'ReauthenticatePage' } }));
vi.mock('./pages/AccountPage.vue', () => ({ default: { name: 'AccountPage' } }));
vi.mock('./pages/ReportProblemPage.vue', () => ({ default: { name: 'ReportProblemPage' } }));
vi.mock('./pages/SignOutPage.vue', () => ({ default: { name: 'SignOutPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('accounts routes.ts', () => {
  it('maps the sign-in\'s errors, its code and 2FA steps and the password reset open to visitors, and the rest behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta])).toEqual([
      // The sign-in itself is the launcher's (`/launch`, the hubs app's: round 17 §2.2; Ioan, 2026-10-15):
      // `/login` only leads there. It signs up an unknown address too: there is no `/signup`.
      ['/login', { auth: false }],
      ['/login/error', { auth: false }],
      // The code mailed at every password sign-in (or to a new account, or an address never proven).
      ['/verify-email', { auth: false }],
      // «Forgot your password?», and the page its mailed link opens (`HEADLESS_FRONTEND_URLS`).
      ['/password/reset', { auth: false }],
      ['/password/reset/key/:resetKey', { auth: false }],
      // The login waits for its second factor: no session yet.
      ['/2fa/authenticate', { auth: false }],
      // The 2FA settings and «Confirm it's you», in the auth card too.
      ['/2fa', { auth: true, chrome: false }],
      ['/reauthenticate', { auth: true, chrome: false }],
      // Account (round 17, PLAN-SAAS §3.6): one address per section, the footer tabbar follows the route.
      ['/dashboard/account', { auth: true }],
      ['/dashboard/account/:tab(profile|security|preferences|api-keys)', { auth: true }],
      // «Report a problem» of the user menu (ACCOUNTS-F38): the account goes with the report.
      ['/dashboard/report-a-problem', { auth: true }],
      // Where the Hub's «Sign out» lands (BASE-F61, hub `base/auth_views.py` SAAS_LOGOUT_PATH): erplora.com asks before
      // closing its own session (ACCOUNTS-F09), in the auth card; open to a visitor, whom it sends to the launcher.
      ['/logout', { auth: false, chrome: false }],
    ]);
  });

  it('sends `/login` (old links, bookmarks) to the launcher\'s sign-in, keeping its query', () => {
    const entry = routes.find((r) => r.path === '/login')!;
    expect(entry.component).toBeUndefined();
    const redirect = entry.redirect as (to: { query: Record<string, string> }) => unknown;
    expect(redirect({ query: { next: '/dashboard/account', notice: 'password_reset' } })).toEqual({
      path: '/launch',
      query: { next: '/dashboard/account', notice: 'password_reset' },
    });
  });

  it('opens Account on its Profile, and hands each section its tab as a prop', () => {
    const entry = routes.find((r) => r.path === '/dashboard/account')!;
    expect(entry.redirect).toBe('/dashboard/account/profile');
    const page = routes.find((r) => r.path.startsWith('/dashboard/account/:tab'))!;
    expect(page.props).toBe(true);
  });

  it('hands the reset page the key of its link as a prop (`key` itself is reserved by Vue)', () => {
    const page = routes.find((r) => r.path === '/password/reset/key/:resetKey')!;
    expect(page.props).toBe(true);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    const pages = {
      '/login/error': 'LoginErrorPage',
      '/verify-email': 'VerifyEmailPage',
      '/password/reset': 'PasswordResetPage',
      '/password/reset/key/:resetKey': 'PasswordResetKeyPage',
      '/2fa/authenticate': 'TwoFactorAuthenticatePage',
      '/2fa': 'TwoFactorSettingsPage',
      '/reauthenticate': 'ReauthenticatePage',
      '/dashboard/account/:tab(profile|security|preferences|api-keys)': 'AccountPage',
      '/dashboard/report-a-problem': 'ReportProblemPage',
      '/logout': 'SignOutPage',
    };
    for (const route of routes.filter((r) => !r.redirect)) {
      expect(typeof route.component, route.path).toBe('function');
      // The stub of that very page: a real one here means a page this file does not stub.
      expect(await load(route), route.path).toEqual({ name: pages[route.path as keyof typeof pages] });
    }
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
