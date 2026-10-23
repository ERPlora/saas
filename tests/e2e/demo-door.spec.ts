// The door of the demo hubs (/demo/, public/demo.py; PLAN-SAAS §3.5, round 2026-10-17) in a real browser,
// under the public web's CSP with zero violations: the home's «Try the demo» leads to it, it offers a demo
// in English and in Spanish at the three viewports, and its button (an ion-button inside a POST form) really
// submits. This server has no Hub (`HUB_INTERNAL_URL` is the private name, unresolvable here), so the press
// lands on the visible «not available» state; the whole walk into a demo hub is the Hub's e2e
// (hub/tests/e2e/demo.spec.ts). The screenshots stay in `.artifacts/demo/` for review.
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { expect, test } from './public-test';

const ARTIFACTS = join(dirname(fileURLToPath(import.meta.url)), '.artifacts', 'demo');
const WIDTHS = [390, 768, 1440];

/** Every CSP violation of the page, however the browser reports it (as public-dark.spec.ts). */
async function watchCsp(page: Page) {
  const reports: string[] = [];
  const consoleErrors: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/csp-report/')) reports.push(request.postData() ?? '');
  });
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) consoleErrors.push(message.text());
  });
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) =>
      w.__csp.push(`${event.violatedDirective} ${event.blockedURI}`),
    );
  });
  return async () => ({
    violations: await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp),
    reports,
    consoleErrors,
  });
}

async function expectNoCspProblems(problems: Awaited<ReturnType<typeof watchCsp>>, where: string) {
  expect(await problems(), where).toEqual({ violations: [], reports: [], consoleErrors: [] });
}

/** The door loaded at each width, captured whole as `demo-<language>-<width>.png`. */
async function captureAtEveryWidth(page: Page, language: string) {
  mkdirSync(ARTIFACTS, { recursive: true });
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    // A fresh load at each width: a full-page capture of a resized page repeats its top.
    await page.reload();
    await expect(page.getByTestId('demo-start')).toBeVisible();
    await page.screenshot({ path: join(ARTIFACTS, `demo-${language}-${width}.png`), fullPage: true });
  }
}

test.describe('in English', () => {
  test.use({ locale: 'en-GB' });

  test('the home leads to the demo door, which offers a demo', async ({ page }) => {
    const problems = await watchCsp(page);

    mkdirSync(ARTIFACTS, { recursive: true });
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');
      await expect(page.locator('section.hero-bg ion-button[href="/demo/"]')).toBeVisible();
      await page.screenshot({ path: join(ARTIFACTS, `home-hero-en-${width}.png`) });
    }
    await page.locator('section.hero-bg ion-button[href="/demo/"]').click();

    await expect(page).toHaveURL(/\/demo\/$/);
    await expect(page.getByTestId('demo-state-idle')).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Try ERPlora without signing up.');
    await expect(page.getByTestId('demo-start')).toContainText('Try the demo');
    await captureAtEveryWidth(page, 'en');
    await expectNoCspProblems(problems, '/demo/ in English');
  });

  test('the button really posts, and an absent Hub is said, not hidden', async ({ page }) => {
    const problems = await watchCsp(page);
    await page.goto('/demo/');

    await page.getByTestId('demo-start').click();

    await expect(page).toHaveURL(/\/demo\/\?state=unavailable$/);
    await expect(page.getByTestId('demo-state-unavailable')).toBeVisible();
    await expect(page.getByText('The demo is not available right now.')).toBeVisible();
    await expect(page.getByTestId('demo-start')).toContainText('Try again');
    await expectNoCspProblems(problems, '/demo/?state=unavailable');
  });
});

test.describe('in Spanish', () => {
  test.use({ locale: 'es-ES' });

  test('the door speaks Spanish', async ({ page }) => {
    const problems = await watchCsp(page);

    await page.goto('/demo/');

    await expect(page.getByTestId('demo-state-idle')).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Prueba ERPlora sin registrarte.');
    await expect(page.getByTestId('demo-start')).toContainText('Prueba la demo');
    await captureAtEveryWidth(page, 'es');
    await expectNoCspProblems(problems, '/demo/ in Spanish');
  });
});
