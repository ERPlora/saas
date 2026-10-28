// FIX-SAAS-SPA-STATIC-PROBES-SET-CSRF-COOKIE in Chrome: on erplora.com a crawler's or a browser's /favicon.ico and a
// scanner's /wp-login.php got the SPA with a 200 and a `csrftoken` cookie. A path that names a file and has no URL of
// its own is now a plain 404 with no shell and no cookie, signed in or not, whether it asks for a page or for
// anything, on the panel's server (DEBUG on) and on the production-like one (DEBUG off: the project's 404 page); a page
// of the panel still opens and sets the cookie its first write sends back. Accounts of panel_seed.py; Businesses at
// 390, 834 and 1440 px.
// flow: saas-spa-static-probes
import type { APIRequestContext } from '@playwright/test';
import { STACK } from '../stack';
import { expect, panelAccount, seedPanel, settled, shot, signIn, test, VIEWPORTS } from './fixtures';

const KEY = 'FIX-SAAS-SPA-STATIC-PROBES-SET-CSRF-COOKIE';
const PROBES = ['/favicon.ico', '/wp-login.php'];
const BROWSER_PAGE = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8';
const ACCEPTS = [BROWSER_PAGE, '*/*'];
/** The public server of the stack: DEBUG off, so Django renders the project's 404 (`templates/404.html`). */
const PRODUCTION_LIKE = `http://127.0.0.1:${STACK.publicPort}`;

/** Each probe, with each Accept: Django's 404, no `Set-Cookie` and none of the shell (its `spa-config`). */
async function expectPlain404s(request: APIRequestContext, who: string): Promise<void> {
  for (const path of PROBES) {
    for (const accept of ACCEPTS) {
      const label = `${who} ${path} with Accept ${accept}`;
      const response = await request.get(path, { headers: { Accept: accept }, maxRedirects: 0 });
      expect(response.status(), label).toBe(404);
      expect(response.headers()['set-cookie'], `${label} sets no cookie`).toBeUndefined();
      expect(await response.text(), `${label} is not the shell`).not.toContain('id="spa-config"');
    }
  }
}

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('saas-spa-static-probes · a probe for a file gets a plain 404 with no cookie, signed in or not, and the panel still opens with its cookie', async ({
  page,
  playwright,
  baseURL,
}) => {
  for (const [server, url] of [
    ['panel', baseURL],
    ['production-like', PRODUCTION_LIKE],
  ] as const) {
    const anonymous = await playwright.request.newContext({ baseURL: url });
    await expectPlain404s(anonymous, `${server}, without a session:`);
    await anonymous.dispose();
  }

  await signIn(page.request, panelAccount('several'));
  await expectPlain404s(page.request, 'signed in:');

  // The page load itself must set the token again: without it the SDK's first write is refused (403).
  await page.context().clearCookies({ name: 'csrftoken' });
  const businesses = await page.goto('/dashboard/businesses');
  expect(businesses?.status(), 'GET /dashboard/businesses').toBe(200);
  await expect(page.getByTestId('businesses-row').first()).toBeVisible();
  const cookies = await page.context().cookies();
  expect(
    cookies.some((cookie) => cookie.name === 'csrftoken'),
    'the panel sets csrftoken',
  ).toBe(true);

  for (const size of VIEWPORTS) {
    await page.setViewportSize(size);
    await settled(page);
    await page.screenshot({ path: shot(`${KEY}-${size.width}`), fullPage: true });
  }
});
