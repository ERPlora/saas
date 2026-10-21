// The billing `routes.ts`: routes → pages and nothing else (main.ts reads the default export). The Store
// sells: it is the web's only, and StorePage itself says so inside the apps («The store is not in the
// app», with its own text: the shell's generic NotInAppPage of `meta.webOnly` cannot say it).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteComponent } from 'vue-router';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';

import routes from './routes';

// The pages, stubbed: this file checks which page each route loads and that it loads it on demand, not
// the page (its own tests mount it). A real page brings its whole graph (Ionic, @erplora/ui): over a
// second idle and past Vitest's 5 s on a loaded machine. The router's navigations load them too.
vi.mock('./pages/StorePage.vue', () => ({ default: { name: 'StorePage' } }));
vi.mock('./pages/BillingPage.vue', () => ({ default: { name: 'BillingPage' } }));
vi.mock('./pages/InvoicePage.vue', () => ({ default: { name: 'InvoicePage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

describe('billing routes.ts', () => {
  it('maps the Store and Billing, one address per section', () => {
    expect(routes.map((r) => [r.path, r.meta])).toEqual([
      ['/store', { auth: true }],
      ['/store/:tab(plans|modules)', { auth: true }],
      ['/billing', { auth: true }],
      ['/billing/:tab(invoices|subscriptions|payment)', { auth: true }],
      ['/billing/invoices/:id', { auth: true }],
    ]);
  });

  it('BILLING-G05: an invoice has its own page, its id as a prop, loaded on demand; not selling: no `webOnly`', async () => {
    const page = routes.find((r) => r.path === '/billing/invoices/:id');
    expect(page?.props).toBe(true);
    expect(page?.meta?.webOnly).toBeUndefined();
    const router = createRouter({ history: createMemoryHistory(), routes });
    expect(router.resolve('/billing/invoices/0193f0a0-0000-7000-8000-000000000000').params).toEqual({ id: '0193f0a0-0000-7000-8000-000000000000' });
    expect(router.resolve('/billing/invoices').params).toEqual({ tab: 'invoices' });
    const loader = page?.component as () => Promise<{ default: RouteComponent }>;
    expect((await loader()).default).toEqual({ name: 'InvoicePage' });
  });

  it('opens Billing on Invoices, keeping what it was opened for (`?business=`, Stripe’s Portal coming back)', () => {
    // The redirect itself, without navigating: a navigation would load the page's chunk (not what this checks).
    const billing = routes.find((r) => r.path === '/billing');
    const redirect = billing?.redirect as (to: { query: Record<string, string> }) => unknown;
    expect(redirect({ query: { business: 'h1' } })).toEqual({ path: '/billing/invoices', query: { business: 'h1' } });
    const router = createRouter({ history: createMemoryHistory(), routes });
    expect(router.resolve('/billing/payment').params).toEqual({ tab: 'payment' });
    expect(router.resolve('/billing/other').matched).toEqual([]);
  });

  it('hands Billing its section as a prop, loaded on demand; it is not selling: no `webOnly`', async () => {
    const billing = routes.find((r) => r.path.startsWith('/billing/:tab'));
    expect(billing?.props).toBe(true);
    expect(billing?.meta?.webOnly).toBeUndefined();
    const loader = billing?.component as () => Promise<{ default: RouteComponent }>;
    expect((await loader()).default).toEqual({ name: 'BillingPage' });
  });

  it('opens the Store on Plans, keeping the business it was opened for', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    await router.push('/store?business=h1');
    expect(router.currentRoute.value.fullPath).toBe('/store/plans?business=h1');
    await router.push('/store/modules');
    expect(router.currentRoute.value.params).toEqual({ tab: 'modules' });
  });

  it('hands the section to the page as a prop (Ionic keeps one view per address), loaded on demand', async () => {
    const store = routes.find((r) => r.path.startsWith('/store/:tab'));
    expect(store?.props).toBe(true);
    expect(typeof store?.component).toBe('function');
    const loader = store?.component as () => Promise<{ default: RouteComponent }>;
    expect((await loader()).default).toEqual({ name: 'StorePage' });
  });

  it('imports types only: Vite hoists the eager glob of main.ts above the shell boot hooks', () => {
    const source = readFileSync(join(HERE, 'routes.ts'), 'utf8');
    expect([...source.matchAll(/^import\s+(?!type\b).*$/gm)]).toEqual([]);
  });
});
