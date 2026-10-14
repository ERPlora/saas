// The businesses panel at the three viewports (working rules §2.4), light and dark, on the web and in
// the app (plan 2026-10-13, «Hecho L1»): every page renders without scrolling sideways (read where
// Ionic scrolls, not on `body`, which it pins; the reader is proved on an overflowing page) nor an
// uncaught error, and leaves a screenshot named as `mockups/saas-panel/screenshots/`
// (`<screen>-<state>[-<section>][-<surface>]-<width>-<theme>.png`) for the supervisor to compare with
// the mockups. They go to `.artifacts/panel/viewports/`, or to `$SHOTS_DIR` when it is set.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { type Browser, type BrowserContext, type Page } from '@playwright/test';

import { businessIdOf, expect, panelAccount, seedPanel, shot, signIn, test, VIEWPORTS } from './fixtures';
import { PANEL_URL } from './project';

const SHOTS_DIR = process.env.SHOTS_DIR ?? join(shot('viewports-dir'), '..', 'viewports');
mkdirSync(SHOTS_DIR, { recursive: true });

interface Screen {
  name: string;
  account: string | null;
  path: string | ((request: BrowserContext['request']) => Promise<string>);
  /** What says the page is painted (not still loading). */
  ready: (page: Page) => ReturnType<Page['getByTestId']>;
}

const bakery = (tab: string) => async (request: BrowserContext['request']) =>
  `/businesses/${await businessIdOf(request, 'Panadería López')}/${tab}`;

const SCREENS: Screen[] = [
  { name: 'launch-signed-out', account: null, path: '/launch', ready: (p) => p.getByTestId('launch-sign-in') },
  { name: 'launch-first', account: 'first', path: '/launch', ready: (p) => p.getByTestId('create-name') },
  { name: 'launch-one', account: 'one', path: '/launch', ready: (p) => p.getByTestId('launch-open') },
  { name: 'launch-several', account: 'several', path: '/launch', ready: (p) => p.getByTestId('launch-business').first() },
  { name: 'launch-first-invited', account: 'invited', path: '/launch', ready: (p) => p.getByTestId('launch-accept') },
  { name: 'businesses-default', account: 'several', path: '/businesses', ready: (p) => p.getByTestId('businesses-row').first() },
  { name: 'businesses-empty', account: 'first', path: '/businesses', ready: (p) => p.getByTestId('businesses-empty') },
  { name: 'businesses-create', account: 'several', path: '/businesses?create=1', ready: (p) => p.getByTestId('create-modal-submit') },
  { name: 'business-default', account: 'several', path: bakery('summary'), ready: (p) => p.getByTestId('summary-plan') },
  { name: 'business-default-members', account: 'several', path: bakery('members'), ready: (p) => p.getByTestId('members-row').first() },
  { name: 'business-default-modules', account: 'several', path: bakery('modules'), ready: (p) => p.getByTestId('business-modules') },
  { name: 'business-default-settings', account: 'several', path: bakery('settings'), ready: (p) => p.getByTestId('danger-zone') },
  { name: 'invitation-default', account: 'several', path: '/invitation', ready: (p) => p.getByTestId('invitation-accept').first() },
  { name: 'invitation-expired', account: 'first', path: '/invitation', ready: (p) => p.getByTestId('invitation-expired') },
];

/** The app surfaces of the mockups: the desktop app at 1440 and the mobile one at 390. */
const APP_SCREENS = ['launch-one', 'business-default', 'businesses-default'];

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

/** Each account signs in once per run (allauth limits sign-ins per minute): its cookies are reused. */
const sessions = new Map<string, Awaited<ReturnType<BrowserContext['storageState']>>>();

async function contextFor(browser: Browser, account: string | null, theme: 'light' | 'dark'): Promise<BrowserContext> {
  const options = { locale: 'es-ES', colorScheme: theme, baseURL: PANEL_URL } as const;
  if (!account) return browser.newContext(options);
  let state = sessions.get(account);
  if (!state) {
    const signing = await browser.newContext(options);
    try {
      await signIn(signing.request, panelAccount(account));
      state = await signing.storageState();
    } finally {
      await signing.close();
    }
    sessions.set(account, state);
  }
  return browser.newContext({ ...options, storageState: state });
}

/**
 * What scrolls sideways on the page on screen: Ionic pins `body` (its width never grows), so the
 * scroll is read where it happens — the page's `ion-content` scroll box (in its shadow) and every
 * DataTable's own scroll box, which also says so with `data-table__scroll--overflow`.
 */
async function sidewaysScroll(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const found: string[] = [];
    const content = shown.querySelector('ion-content');
    const scroll = content?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');
    if (scroll && scroll.scrollWidth > scroll.clientWidth + 1) found.push(`ion-content ${scroll.scrollWidth} > ${scroll.clientWidth}`);
    for (const table of shown.querySelectorAll<HTMLElement>('.data-table__scroll')) {
      if (table.scrollWidth > table.clientWidth + 1) found.push(`data-table ${table.scrollWidth} > ${table.clientWidth}`);
      if (table.classList.contains('data-table__scroll--overflow')) found.push('data-table__scroll--overflow');
    }
    return found;
  });
}

/** Settled: the fonts loaded and no transition of Ionic running (endless spinners aside). */
async function settled(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every((animation) => animation.playState !== 'running' || animation.effect?.getTiming().iterations === Infinity),
  );
}

async function capture(page: Page, screen: Screen, path: string, width: number, file: string, errors: string[]) {
  const height = VIEWPORTS.find((v) => v.width === width)?.height ?? 900;
  await page.setViewportSize({ width, height });
  await page.goto(path);
  await expect(screen.ready(page)).toBeVisible();
  await settled(page);
  expect(await sidewaysScroll(page), `${file} scrolls sideways`).toEqual([]);
  await page.screenshot({ path: join(SHOTS_DIR, file), fullPage: true });
  expect(errors, file).toEqual([]);
}

/** One context per screen and theme, always closed (a context left open ends in «Target crashed»). */
async function withContext(browser: Browser, account: string | null, theme: 'light' | 'dark', run: (context: BrowserContext) => Promise<void>) {
  const context = await contextFor(browser, account, theme);
  try {
    await run(context);
  } finally {
    await context.close();
  }
}

test('the sideways-scroll reader catches a page that overflows (the check of the check)', async ({ browser }) => {
  await withContext(browser, 'several', 'light', async (context) => {
    const page = await context.newPage();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/businesses');
    await expect(page.getByTestId('businesses-row').first()).toBeVisible();
    await settled(page);
    expect(await sidewaysScroll(page)).toEqual([]);
    await page.evaluate(() => {
      const wide = document.createElement('div');
      wide.style.width = '2000px';
      wide.style.height = '10px';
      document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) .list-stack')?.append(wide);
    });
    expect((await sidewaysScroll(page)).join()).toMatch(/^ion-content \d+ > \d+$/);
  });
});

/** The widths where a table folds (W-19): phone, tablet both ways, the laptops and the desktop. */
const TABLE_WIDTHS = [390, 834, 1024, 1180, 1280, 1366, 1440];

for (const name of ['businesses-default', 'business-default-members']) {
  test(`${name}: the table fits its box at ${TABLE_WIDTHS.join(', ')} px (it folds, it never scrolls sideways)`, async ({ browser }) => {
    const screen = SCREENS.find((candidate) => candidate.name === name)!;
    await withContext(browser, screen.account, 'light', async (context) => {
      const path = typeof screen.path === 'string' ? screen.path : await screen.path(context.request);
      const page = await context.newPage();
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(String(error)));
      for (const width of TABLE_WIDTHS) {
        await capture(page, screen, path, width, `${name}-fit-${width}-light.png`, errors);
        await expect(page.locator('.data-table__scroll--overflow')).toHaveCount(0);
      }
    });
  });
}

for (const theme of ['light', 'dark'] as const) {
  for (const screen of SCREENS) {
    test(`${screen.name} at 390, 834 and 1440 px, ${theme}`, async ({ browser }) => {
      await withContext(browser, screen.account, theme, async (context) => {
        const path = typeof screen.path === 'string' ? screen.path : await screen.path(context.request);
        const page = await context.newPage();
        const errors: string[] = [];
        page.on('pageerror', (error) => errors.push(String(error)));
        for (const { width } of VIEWPORTS) await capture(page, screen, path, width, `${screen.name}-${width}-${theme}.png`, errors);
      });
    });
  }

  for (const name of APP_SCREENS) {
    test(`${name} inside the apps (desktop 1440, mobile 390), ${theme}`, async ({ browser }) => {
      const screen = SCREENS.find((candidate) => candidate.name === name)!;
      await withContext(browser, screen.account, theme, async (context) => {
        const base = typeof screen.path === 'string' ? screen.path : await screen.path(context.request);
        const page = await context.newPage();
        const errors: string[] = [];
        page.on('pageerror', (error) => errors.push(String(error)));
        for (const [surface, width] of [['desktop', 1440], ['mobile', 390]] as const) {
          const path = `${base}${base.includes('?') ? '&' : '?'}surface=${surface}`;
          await capture(page, screen, path, width, `${name}-${surface}-${width}-${theme}.png`, errors);
          await expect(page.locator('html')).toHaveClass(/in-app-shell/);
        }
      });
    });
  }
}
