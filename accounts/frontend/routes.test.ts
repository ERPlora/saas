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
      // Its own frame (the auth card of the template), never the shell's menu.
      ['/launch', { auth: true, chrome: false }],
      // Where the auth gate sends a visitor without a session.
      ['/login', { auth: false }],
      ['/login/error', { auth: false }],
      // The login waits for its second factor: no session yet.
      ['/2fa/authenticate', { auth: false }],
      // The 2FA settings and «Confirm it's you», in the auth card too.
      ['/2fa', { auth: true, chrome: false }],
      ['/reauthenticate', { auth: true, chrome: false }],
    ]);
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    const pages = {
      '/launch': (await import('./pages/LaunchPage.vue')).default,
      '/login': (await import('./pages/LoginPage.vue')).default,
      '/login/error': (await import('./pages/LoginErrorPage.vue')).default,
      '/2fa/authenticate': (await import('./pages/TwoFactorAuthenticatePage.vue')).default,
      '/2fa': (await import('./pages/TwoFactorSettingsPage.vue')).default,
      '/reauthenticate': (await import('./pages/ReauthenticatePage.vue')).default,
    };
    for (const route of routes) {
      expect(typeof route.component, route.path).toBe('function');
      expect(await load(route), route.path).toBe(pages[route.path as keyof typeof pages]);
    }
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
