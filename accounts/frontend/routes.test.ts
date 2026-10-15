// The accounts `routes.ts`: routes → pages and nothing else (main.ts reads the default export).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import routes from './routes';

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
      ['/account', { auth: true }],
      ['/account/:tab(profile|security|preferences|api-keys)', { auth: true }],
    ]);
  });

  it('sends `/login` (old links, bookmarks) to the launcher\'s sign-in, keeping its query', () => {
    const entry = routes.find((r) => r.path === '/login')!;
    expect(entry.component).toBeUndefined();
    const redirect = entry.redirect as (to: { query: Record<string, string> }) => unknown;
    expect(redirect({ query: { next: '/account', notice: 'password_reset' } })).toEqual({
      path: '/launch',
      query: { next: '/account', notice: 'password_reset' },
    });
  });

  it('opens Account on its Profile, and hands each section its tab as a prop', () => {
    const entry = routes.find((r) => r.path === '/account')!;
    expect(entry.redirect).toBe('/account/profile');
    const page = routes.find((r) => r.path.startsWith('/account/:tab'))!;
    expect(page.props).toBe(true);
  });

  it('hands the reset page the key of its link as a prop (`key` itself is reserved by Vue)', () => {
    const page = routes.find((r) => r.path === '/password/reset/key/:resetKey')!;
    expect(page.props).toBe(true);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    const pages = {
      '/login/error': (await import('./pages/LoginErrorPage.vue')).default,
      '/verify-email': (await import('./pages/VerifyEmailPage.vue')).default,
      '/password/reset': (await import('./pages/PasswordResetPage.vue')).default,
      '/password/reset/key/:resetKey': (await import('./pages/PasswordResetKeyPage.vue')).default,
      '/2fa/authenticate': (await import('./pages/TwoFactorAuthenticatePage.vue')).default,
      '/2fa': (await import('./pages/TwoFactorSettingsPage.vue')).default,
      '/reauthenticate': (await import('./pages/ReauthenticatePage.vue')).default,
      '/account/:tab(profile|security|preferences|api-keys)': (await import('./pages/AccountPage.vue')).default,
    };
    for (const route of routes.filter((r) => !r.redirect)) {
      expect(typeof route.component, route.path).toBe('function');
      expect(await load(route), route.path).toBe(pages[route.path as keyof typeof pages]);
    }
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
