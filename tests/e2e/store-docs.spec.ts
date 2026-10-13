// Spec §6: the documentation tab of an app (/apps/<id>/docs/) paints its ```mermaid``` diagram under
// the public web's CSP with ZERO violations. Mermaid writes its SVG with inline styles, and
// frontend/public.ts loads it only when the page has a `pre.mermaid`. Violations are caught three
// ways: the `securitypolicyviolation` event, the console and the reports the browser would POST to
// /csp-report/. If this fails, the rule of spec §6 applies: the narrowest change (one directive, only
// on the documentation pages) in public/csp.py, written down in the plan.
//
// The second spec drives the store's search in a real browser: `ion-searchbar` inside a GET form,
// which no server test can submit.
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page, expect, test } from '@playwright/test';

const APP = 'e2e_store_docs';
const ARTIFACTS = join(dirname(fileURLToPath(import.meta.url)), '.artifacts');

type Violation = { directive: string; blocked: string; sample: string };

/** Every CSP violation of the page, however the browser reports it. */
async function watchCsp(page: Page) {
  const reports: string[] = [];
  const cspConsole: string[] = [];
  const pageErrors: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/csp-report/')) reports.push(request.postData() ?? '');
  });
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) cspConsole.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: unknown[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) =>
      w.__csp.push({ directive: event.violatedDirective, blocked: event.blockedURI, sample: event.sample }),
    );
  });
  return {
    reports,
    cspConsole,
    pageErrors,
    violations: () => page.evaluate(() => (window as unknown as { __csp: Violation[] }).__csp),
  };
}

function shot(name: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  return join(ARTIFACTS, `${name}.png`);
}

test('the documentation tab paints its Mermaid diagram with no CSP violation', async ({ page }) => {
  const csp = await watchCsp(page);

  const response = await page.goto(`/apps/${APP}/docs/`);

  expect(response?.status()).toBe(200);
  const policy = response?.headers()['content-security-policy'] ?? '';
  // The public web's own policy (public/csp.py), enforced: no 'strict-dynamic', no Trusted Types.
  expect(policy).toContain("style-src 'self' 'unsafe-inline'");
  expect(policy).not.toContain('strict-dynamic');
  expect(policy).not.toContain('require-trusted-types-for');

  const diagram = page.locator('pre.mermaid svg');
  await expect(diagram).toBeVisible();
  await expect(page.locator('pre.mermaid')).toContainText('Ticket abierto');
  await expect(page.locator('pre.mermaid')).toContainText('Factura VeriFactu');
  // The English page serves the Spanish document with its notice (spec §5.3).
  await expect(page.getByText('This documentation is only available in Spanish.')).toBeVisible();
  await expect(page.locator('article.ep-store-docs[lang="es"]')).toBeVisible();

  await page.waitForTimeout(1500); // late violations (lazy chunks, fonts, styles)
  await page.screenshot({ path: shot('store-docs--mermaid'), fullPage: true });

  expect(await csp.violations()).toEqual([]);
  expect(csp.reports).toEqual([]);
  expect(csp.cspConsole).toEqual([]);
  expect(csp.pageErrors).toEqual([]);
});

test('the store searches from its searchbar and opens the app', async ({ page }) => {
  const csp = await watchCsp(page);

  await page.goto('/apps/');
  const search = page.locator('ion-searchbar[name="q"] input');
  await search.fill('E2E Store');
  await search.press('Enter');

  await expect(page).toHaveURL(/\/apps\/\?q=E2E\+Store$/);
  const card = page.locator(`a.ep-product-card[href="/apps/${APP}/"]`);
  await expect(card).toBeVisible();
  await page.screenshot({ path: shot('store-list--search'), fullPage: true });
  await card.click();

  await expect(page).toHaveURL(new RegExp(`/apps/${APP}/$`));
  await expect(page.locator('h1.ep-hero__title')).toHaveText('E2E Store Docs');
  await page.getByRole('link', { name: 'Documentation' }).click();
  await expect(page.locator('pre.mermaid svg')).toBeVisible();

  expect(await csp.violations()).toEqual([]);
  expect(csp.reports).toEqual([]);
  expect(csp.pageErrors).toEqual([]);
});

// Phone, tablet and desktop (working rules §2.4): nothing wider than the screen, in English and Spanish.
for (const width of [390, 834, 1440]) {
  test(`the store's pages fit ${width} px`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const language of ['en', 'es']) {
      // The language cookie of the public web (plan §3.a).
      await context.addCookies([{ name: '_lang', value: language, url: test.info().project.use.baseURL as string }]);
      for (const [name, path] of [
        ['list', '/apps/'],
        ['overview', `/apps/${APP}/`],
        ['docs', `/apps/${APP}/docs/`],
      ]) {
        await page.goto(path);
        await expect(page.locator('h1').first()).toBeVisible();
        if (name === 'docs') await expect(page.locator('pre.mermaid svg')).toBeVisible();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow, `${path} (${language}) overflows ${width} px`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: shot(`store-${name}--${language}-${width}`), fullPage: true });
      }
    }
  });
}
