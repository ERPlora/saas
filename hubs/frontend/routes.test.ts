// The hubs `routes.ts`: routes → pages and nothing else (main.ts reads the default export).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent, RouteRecordRaw } from 'vue-router';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. The router's navigations load them too.
vi.mock('./pages/LaunchPage.vue', () => ({ default: { name: 'LaunchPage' } }));
vi.mock('./pages/BusinessListPage.vue', () => ({ default: { name: 'BusinessListPage' } }));
vi.mock('./pages/BusinessPage.vue', () => ({ default: { name: 'BusinessPage' } }));
vi.mock('./pages/InvitationPage.vue', () => ({ default: { name: 'InvitationPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

async function load(r: RouteRecordRaw): Promise<RouteComponent> {
  const loader = r.component as () => Promise<{ default: RouteComponent }>;
  return (await loader()).default;
}

describe('hubs routes.ts', () => {
  it('maps the entry (open to visitors, its own frame), the businesses, a business by section and the invitations', () => {
    expect(routes.map((r) => [r.path, r.meta])).toEqual([
      // The entry: signed out it asks to sign in, so it is open; never the shell's menu.
      ['/launch', { auth: false, chrome: false }],
      ['/businesses', { auth: true }],
      // A business opens on its Summary; each section has its address (the tabbar follows it).
      ['/businesses/:id', { auth: true }],
      ['/businesses/:id/:tab(summary|members|modules|settings)', { auth: true }],
      // The invitation's email links to /invitation; a banner links to one of them.
      ['/invitation', { auth: true, chrome: false }],
      ['/invitations/:id', { auth: true, chrome: false }],
    ]);
  });

  // flow: HUBS-F02 (HUBS-G66) and HUBS-F12 (HUBS-G71): `ERPlora/app` boots on /shell/ and never changes it
  // (working-rules §12; PLAN-SAAS bloque 3: «/shell/, alias de /launch»).
  it("serves the launcher at the installed app's start, /shell/", async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    const launcher = await load(routes.find((r) => r.path === '/launch') as RouteRecordRaw);
    for (const path of ['/shell/', '/shell', '/shell/?choose=1']) {
      await router.push(path);
      const [matched] = router.currentRoute.value.matched;
      // The router has loaded the page by now: the launcher's.
      expect(matched?.components?.default, path).toBe(launcher);
      expect(matched?.meta, path).toEqual({ auth: false, chrome: false });
    }
  });

  it('opens a business on its Summary', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    await router.push('/businesses/h1');
    expect(router.currentRoute.value.fullPath).toBe('/businesses/h1/summary');
    expect(router.currentRoute.value.params).toEqual({ id: 'h1', tab: 'summary' });
    await router.push('/businesses/h1/members');
    expect(router.currentRoute.value.params).toEqual({ id: 'h1', tab: 'members' });
  });

  it('loads each page on demand (one chunk per page), not at boot', async () => {
    const pages = {
      '/launch': 'LaunchPage',
      '/businesses': 'BusinessListPage',
      '/businesses/:id/:tab(summary|members|modules|settings)': 'BusinessPage',
      '/invitation': 'InvitationPage',
      '/invitations/:id': 'InvitationPage',
    };
    for (const route of routes.filter((r) => !r.redirect)) {
      expect(typeof route.component, route.path).toBe('function');
      // The stub of that very page: a real one here means a page this file does not stub.
      expect(await load(route), route.path).toEqual({ name: pages[route.path as keyof typeof pages] });
    }
  });

  it('hands the business and its section to the page as props (Ionic keeps one view per address)', () => {
    const business = routes.find((r) => r.path.startsWith('/businesses/:id/'));
    expect(business?.props).toBe(true);
    expect(routes.find((r) => r.path === '/invitations/:id')?.props).toBe(true);
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
