// The panel's paths, named once (`paths.ts`). The launcher's: the sign-in lives there (round 19, PLAN-SAAS §3.7), so
// every page, component and the entry that sends a visitor to it imports `LAUNCHER` instead of spelling the path
// under a name of its own (`LOGIN`, `SIGN_IN`, `HERE`…). The panel's pages live under `PANEL`, `/dashboard`
// (FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX): every page shown with the panel's menu, and nothing else (the launcher, the
// sign-in's pages and the invitations stay at the root). Only the `routes.ts` files spell the paths: they import types
// only (main.test.ts), so they cannot import a value.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RouteRecordRaw } from 'vue-router';
import { describe, expect, it } from 'vitest';

import billingRoutes from '../../billing/frontend/routes';
import hubRoutes from '../../hubs/frontend/routes';
import accountRoutes from './routes';
import { ACCOUNT, BILLING, BUSINESSES, LAUNCHER, PANEL, REPORT_PROBLEM, STORE } from './paths';

const SAAS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
/** The panel's frontends (`vite.config.ts` FRONTEND_APPS) and the entry. */
const DIRS = ['accounts/frontend', 'hubs/frontend', 'billing/frontend', 'fiscal/frontend', 'frontend'].map((dir) => join(SAAS_DIR, dir));
/** The launcher's path as a string literal in code (`'/launch'`, `"/launch"`, `'/launch?…'`). */
const SPELLED = /['"]\/launch(?=['"?#])/;
/** A page of the panel spelled as a literal in code, under `/dashboard` or at the root where it lived before
 *  (`'/businesses'`, `"/store/plans"`, `` `/billing/invoices/${id}` ``, `router-link="/account"`). */
const PANEL_SPELLED = /['"`]\/(?:dashboard|businesses|account|billing|store|report-a-problem)(?=[/'"`?#])/;
const ROUTES: RouteRecordRaw[] = [...hubRoutes, ...accountRoutes, ...billingRoutes];

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return ['node_modules', 'dist', 'generated', '__tests__'].includes(entry.name) ? [] : sources(path);
    }
    const code = /\.(ts|vue)$/.test(entry.name) && !entry.name.endsWith('.test.ts');
    return code && entry.name !== 'routes.ts' && entry.name !== 'paths.ts' ? [path] : [];
  });
}

/** The code without its comments, which may name a path to say what a page is (`// Businesses (`/dashboard/…`)`). */
const withoutComments = (text: string) =>
  text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/(^|\s)\/\/.*$/gm, '$1');

const spelledIn = (pattern: RegExp) =>
  DIRS.flatMap(sources)
    .filter((file) => pattern.test(withoutComments(readFileSync(file, 'utf8'))))
    .map((file) => relative(SAAS_DIR, file));

describe('LAUNCHER', () => {
  it('is the path of the launcher route, where the sign-in lives', () => {
    expect(LAUNCHER).toBe('/launch');
    expect(hubRoutes.map((route) => route.path)).toContain(LAUNCHER);
  });

  it('is the only spelling of the path outside the routes files', () => {
    expect(spelledIn(SPELLED)).toEqual([]);
  });
});

// flow: HUBS-F10 (the panel's home under /dashboard, where «Go to the panel» lands).
describe('PANEL', () => {
  it('is /dashboard, and each page of the panel is a route under it', () => {
    expect(PANEL).toBe('/dashboard');
    expect([BUSINESSES, STORE, BILLING, ACCOUNT, REPORT_PROBLEM]).toEqual([
      '/dashboard/businesses',
      '/dashboard/store',
      '/dashboard/billing',
      '/dashboard/account',
      '/dashboard/report-a-problem',
    ]);
    const paths = ROUTES.map((route) => route.path);
    for (const page of [BUSINESSES, STORE, BILLING, ACCOUNT, REPORT_PROBLEM]) expect(paths, page).toContain(page);
  });

  it('holds every page shown with the panel\'s menu, and none of the sign-in, the launcher or the invitations', () => {
    // «Panel» = what the shell paints with its menu: behind a session and not in a frame of its own (`chrome: false`).
    const panel = (route: RouteRecordRaw) => route.meta?.auth !== false && route.meta?.chrome !== false;
    const misplaced = ROUTES.filter((route) => panel(route) !== route.path.startsWith(`${PANEL}/`) && route.path !== PANEL);
    expect(misplaced.map((route) => route.path)).toEqual([]);
  });

  it('/dashboard itself opens Businesses, the panel\'s home', () => {
    const home = ROUTES.find((route) => route.path === '/dashboard');
    expect(home?.redirect).toBe('/dashboard/businesses');
    expect(home?.redirect).toBe(BUSINESSES);
  });

  it('is the only way the code names a page of the panel outside the routes files', () => {
    expect(spelledIn(PANEL_SPELLED)).toEqual([]);
  });
});
