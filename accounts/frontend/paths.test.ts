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
import { beforeAll, describe, expect, it, vi } from 'vitest';

import billingRoutes from '../../billing/frontend/routes';
import hubRoutes from '../../hubs/frontend/routes';
import accountRoutes from './routes';
import { ACCOUNT, BILLING, BUSINESSES, LAUNCHER, PANEL, REPORT_PROBLEM, STORE } from './paths';

// The real `readdirSync` and `readFileSync`, watched: the guardrails search the frontends read once (see `beforeAll`).
vi.mock('node:fs', async (importOriginal) => {
  const fs = await importOriginal<typeof import('node:fs')>();
  return { ...fs, readdirSync: vi.fn(fs.readdirSync), readFileSync: vi.fn(fs.readFileSync) };
});

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

/** Each file of the frontends (relative to the SaaS) and its code without comments, read once per run. */
let code: ReadonlyArray<{ readonly file: string; readonly text: string }> = [];

// Reads every file of the panel's frontends from the disk, so its time is the machine's: read again inside each
// guardrail, it went past Vitest's 5 s (5.3 s) in `pnpm test` beside 20 busy cores (load ~70, 2026-10-28). Read once
// here, with the limit of the guardrails that read the whole tree (60 s, vite.config.test.ts and
// eslint.config.test.ts); each guardrail only searches it in memory (~1 ms) and keeps Vitest's 5 s. Starved (load ~65,
// 2026-10-29) the two old reads took 85 s and 29 s and this one over 60 s: no limit holds that.
beforeAll(() => {
  code = DIRS.flatMap(sources).map((path) => ({
    file: relative(SAAS_DIR, path),
    text: withoutComments(readFileSync(path, 'utf8')),
  }));
}, 60_000);

const spelledIn = (pattern: RegExp) => code.filter(({ text }) => pattern.test(text)).map(({ file }) => file);

describe('the code the guardrails search', () => {
  it('is read from the disk once, before the tests: each guardrail searches it in memory', () => {
    vi.mocked(readdirSync).mockClear();
    vi.mocked(readFileSync).mockClear();
    spelledIn(SPELLED);
    spelledIn(PANEL_SPELLED);
    expect(vi.mocked(readdirSync).mock.calls.length, 'directories listed').toBe(0);
    expect(vi.mocked(readFileSync).mock.calls.length, 'files read').toBe(0);
  });

  it("is every frontend's code, without its comments", () => {
    const files = spelledIn(/(?:)/);
    // Written out, not taken from `DIRS`: a frontend dropped from it would leave the guardrails blind to it.
    const frontends = ['accounts/frontend', 'hubs/frontend', 'billing/frontend', 'fiscal/frontend', 'frontend'];
    expect(frontends.filter((dir) => !files.some((file) => file.startsWith(`${dir}/`)))).toEqual([]);
    expect(files).toEqual(expect.arrayContaining(['frontend/main.ts', 'accounts/frontend/pages/AccountPage.vue']));
    expect(spelledIn(/\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->/)).toEqual([]);
    // Only the comments go: the code between two of them is still searched.
    const between = withoutComments(`/* a */ '/launch' /* b */ <!-- c --> '/dashboard' <!-- d -->`);
    expect([SPELLED.test(between), PANEL_SPELLED.test(between)]).toEqual([true, true]);
  });
});

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
