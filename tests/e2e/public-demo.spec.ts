// The demo's door on erplora.com, part 3 (APP-PUBLIC-3, public/WORKBOOK.md PUBLIC-F27…F37), in a real Chrome under
// the production CSP with zero violations: the home, the menu and the short address (/try/) lead to it; its card in
// every state a visitor can meet without a Hub behind it (offered, not available, could not open, full, too many from
// the connection, ended), each with its way out to «Start free»; and a press that finds no Hub is said, not kept.
// Each screen is captured at 390×844, 834×1112 and 1440×900 as `APP-PUBLIC-3-<key>-<width>.png` in `.artifacts/`.
//
// What needs a Hub is not here: nobody plays it for these specs (the waiting door is demo-wait.spec.ts). The walk
// into a demo — created, «Opening your demo…», the shell as «Demo», «Back to my demo», ended → 410 → the door — is
// the Hub's tests/e2e/demo.spec.ts, run with this SaaS as its SaaS. The switched-off door (PUBLIC-G58) needs a server
// with DEMO_ENABLED off: public/tests/test_demo.py renders it.
// flow: PUBLIC-G53 PUBLIC-G57 PUBLIC-G59 PUBLIC-G60 PUBLIC-G61 PUBLIC-G63
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { horizontalOverflow } from './horizontal-overflow';
import { expect, test } from './public-test';

const HERE = dirname(fileURLToPath(import.meta.url));
const ARTIFACTS = join(HERE, '.artifacts');
const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
  { width: 1440, height: 900 },
];
const DOOR = '/demo/';

/** Every CSP violation and page error, however the browser reports it (as public-web-2.spec.ts). */
async function watch(page: Page) {
  const reports: string[] = [];
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/csp-report/')) reports.push(request.postData() ?? '');
  });
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) =>
      w.__csp.push(`${event.violatedDirective} ${event.blockedURI}`),
    );
  });
  return async (where: string) => {
    const violations = await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
    expect({ violations, reports, consoleErrors, pageErrors }, where).toEqual({
      violations: [],
      reports: [],
      consoleErrors: [],
      pageErrors: [],
    });
  };
}

/** The door's state (`data-testid="demo-state-<state>"`, public/demo.py). */
const card = (page: Page, state: string) => page.getByTestId(`demo-state-${state}`);
const startButton = (page: Page) => page.getByTestId('demo-start');
/**
 * The texts of the card's «Start free», as its button or as the link under it: in the light DOM only (an
 * `ion-button` with `href` draws its own `<a>` in its shadow root, which a locator would count twice).
 */
const startFree = (page: Page, state: string) =>
  card(page, state).evaluate((element) =>
    [...element.querySelectorAll('[href="/launch"]')].map((link) => (link.textContent ?? '').trim()),
  );

/** `path` at the three viewports, each loaded afresh, captured whole as `APP-PUBLIC-3-<key>-<width>.png`. */
async function captureEverywhere(page: Page, path: string, key: string, state: string) {
  mkdirSync(ARTIFACTS, { recursive: true });
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto(path);
    await expect(card(page, state)).toBeVisible();
    expect(await startFree(page, state), `${path}: one «Start free»`).toHaveLength(1);
    const overflow = await horizontalOverflow(page);
    expect(overflow, `${path} overflows sideways at ${viewport.width}px`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: join(ARTIFACTS, `APP-PUBLIC-3-${key}-${viewport.width}.png`), fullPage: true });
  }
}

test.describe('in English', () => {
  test.use({ locale: 'en-GB' });

  test('PUBLIC-G53 the home, the menu and the short address lead to the door, which only offers a demo', async ({
    page,
  }) => {
    const clean = await watch(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.goto('/');
    await expect(page.locator('nav ion-button[href="/demo/"]')).toContainText('Try the demo');
    await expect(page.locator('section.hero-bg ion-button[href="/demo/"]')).toBeVisible();
    await page.locator('section.hero-bg ion-button[href="/demo/"]').click();

    await expect(page).toHaveURL(/\/demo\/$/);
    await expect(card(page, 'idle')).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Try ERPlora without signing up.');
    await expect(card(page, 'idle')).toContainText('No account and no card');
    await expect(startButton(page)).toContainText('Try the demo');

    const short = await page.goto('/try/');
    expect(short?.status()).toBe(200);
    expect(page.url()).toMatch(/\/try\/$/);
    await expect(card(page, 'idle')).toBeVisible();
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', /\/demo\/$/);

    await captureEverywhere(page, DOOR, 'PUBLIC-G53', 'idle');
    await captureEverywhere(page, '/try/', 'PUBLIC-G53-try', 'idle');
    await clean('the door');
  });

  test('PUBLIC-G57 a press that finds no Hub says the demo is not available, and pressing again asks again', async ({
    page,
  }) => {
    const clean = await watch(page);
    await page.goto(DOOR);

    await startButton(page).click();

    await expect(page).toHaveURL(/\/demo\/\?state=unavailable$/);
    await expect(card(page, 'unavailable')).toContainText('The demo is not available right now.');
    await expect(startButton(page)).toContainText('Try again');
    await expect(page.locator('ion-button', { hasText: 'Back to my demo' })).toHaveCount(0);

    // The failed try is not this browser's demo: «Try again» asks the Hub again, it is not stuck on a broken one.
    await startButton(page).click();
    await expect(page).toHaveURL(/\/demo\/\?state=unavailable$/);
    await expect(card(page, 'unavailable')).toBeVisible();

    await captureEverywhere(page, `${DOOR}?state=unavailable`, 'PUBLIC-G57', 'unavailable');
    await captureEverywhere(page, `${DOOR}?state=failed`, 'PUBLIC-G57-failed', 'failed');
    await expect(card(page, 'failed')).toContainText('We could not open your demo. Try again.');
    await clean('the door that could not open a demo');
  });

  test('PUBLIC-G59 every demo taken: try again, or start free', async ({ page }) => {
    const clean = await watch(page);

    await page.goto(`${DOOR}?state=full`);

    await expect(card(page, 'full')).toContainText('The demo is full right now. Try again in a few minutes.');
    await expect(startButton(page)).toContainText('Try again');
    await expect(card(page, 'full')).toContainText('Want to keep what you do? Start free: it takes the same minute.');
    await captureEverywhere(page, `${DOOR}?state=full`, 'PUBLIC-G59', 'full');
    await clean('the full door');
  });

  test('PUBLIC-G60 too many from the connection: no retry, only start free', async ({ page }) => {
    const clean = await watch(page);

    await page.goto(`${DOOR}?state=throttled`);

    await expect(card(page, 'throttled')).toContainText(
      'Too many demos from your network. Please try again in a little while.',
    );
    await expect(startButton(page)).toHaveCount(0);
    expect(await startFree(page, 'throttled')).toEqual(['Start free']);
    await captureEverywhere(page, `${DOOR}?state=throttled`, 'PUBLIC-G60', 'throttled');
    await clean('the throttled door');
  });

  test('PUBLIC-G61 an ended demo is said, and another one is offered without starting by itself', async ({ page }) => {
    const clean = await watch(page);

    await page.goto(`${DOOR}?state=expired`);

    await expect(card(page, 'expired')).toContainText('This demo has ended. Start another one.');
    await expect(startButton(page)).toContainText('Start another demo');
    await expect(page).toHaveURL(/\?state=expired$/);
    await captureEverywhere(page, `${DOOR}?state=expired`, 'PUBLIC-G61', 'expired');
    await clean('the door of an ended demo');
  });

  test('PUBLIC-G63 «Start free» from the door leads to the same entrance as every other one', async ({ page }) => {
    for (const state of ['idle', 'unavailable', 'failed', 'full', 'throttled', 'expired']) {
      await page.goto(state === 'idle' ? DOOR : `${DOOR}?state=${state}`);
      expect(await startFree(page, state), state).toEqual(['Start free']);
    }
    await page.goto(DOOR);
    const entrance = await page.request.get('/launch');
    expect(entrance.status()).toBe(200);
  });
});

test.describe('in Spanish', () => {
  test.use({ locale: 'es-ES' });

  test('PUBLIC-G53 PUBLIC-G59 PUBLIC-G60 PUBLIC-G61 the door speaks Spanish in every state', async ({ page }) => {
    const clean = await watch(page);
    const says: [string, string][] = [
      ['idle', 'Prueba la demo'],
      ['unavailable', 'La demo no está disponible ahora mismo.'],
      ['failed', 'No hemos podido abrir tu demo. Vuelve a intentarlo.'],
      ['full', 'La demo está llena ahora mismo. Vuelve a intentarlo en unos minutos.'],
      ['throttled', 'Demasiadas demos desde tu red. Vuelve a intentarlo dentro de un rato.'],
      ['expired', 'Esta demo ha terminado. Empieza otra.'],
    ];
    for (const [state, text] of says) {
      await page.goto(state === 'idle' ? DOOR : `${DOOR}?state=${state}`);
      await expect(card(page, state), state).toContainText(text);
      expect(await startFree(page, state), state).toEqual(['Empieza gratis']);
    }
    await captureEverywhere(page, `${DOOR}?state=expired`, 'PUBLIC-G61-es', 'expired');
    await clean('the door in Spanish');
  });
});
