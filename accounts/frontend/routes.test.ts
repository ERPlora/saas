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
  it('maps the sign-in, its errors and its 2FA step open to visitors, and the rest behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta])).toEqual([
      // Where the auth gate sends a visitor without a session. (The entry, `/launch`, is the hubs
      // app's: round 17 §2.2.)
      ['/login', { auth: false }],
      ['/login/error', { auth: false }],
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

  it('opens Account on its Profile, and hands each section its tab as a prop', () => {
    const entry = routes.find((r) => r.path === '/account')!;
    expect(entry.redirect).toBe('/account/profile');
    const page = routes.find((r) => r.path.startsWith('/account/:tab'))!;
    expect(page.props).toBe(true);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    const pages = {
      '/login': (await import('./pages/LoginPage.vue')).default,
      '/login/error': (await import('./pages/LoginErrorPage.vue')).default,
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
