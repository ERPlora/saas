// `signInAs` (fixtures.ts): changing account with a page of the panel open, played without load or repetition.
//
// The danger is the page that stays open. Once its cookies are gone its stream gets a 401, the SDK reloads it
// (host-closed.ts) and the launcher asks `GET auth/session`. If that request leaves with the cookie of the sign-in in
// progress (the session of the password step) and Django answers it after the code is confirmed, that session no longer
// exists (the sign-in cycled its key), so SessionMiddleware deletes `sessionid`, which by then is the new account's:
// the next page shows the login form.
//
// A 401 of the stream that merely arrives after the code loses nothing: the reload goes out with the new cookie. So
// does an `auth/session` held with `route.continue()`, since Chrome attaches the cookies when it is released. That is
// why the held request is replayed by hand with the cookie it left with.
import type { Page, Route } from '@playwright/test';

import { CONFIRM_CODE_API, expect, panelAccount, seedPanel, sessionOf, settled, signIn, signInAs, test } from './fixtures';

const STREAM = /\/api\/live\?/;
const SESSION_API = /\/_allauth\/browser\/v1\/auth\/session$/;
const SESSION_ENDED = {
  status: 401,
  contentType: 'application/json',
  body: JSON.stringify({ error: { code: 'unauthorized', message: 'Sign in.' } }),
};

const NEXT_ACCOUNT = panelAccount('one');

const shown = (page: Page) => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();
const firstBusiness = (page: Page) => shown(page).getByTestId('businesses-row').first();

function signal(): { reached: Promise<void>; reach: () => void } {
  let reach!: () => void;
  const reached = new Promise<void>((resolve) => {
    reach = resolve;
  });
  return { reached, reach };
}

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

/**
 * Runs `changeAccount` with a page of the panel open, whose stream gets its 401 between the password and the code and
 * whose `auth/session`, if it asks, is answered after the code. Returns the `Set-Cookie` lines of that late answer: none
 * when the page was no longer there to ask.
 */
async function changeAccountWithAPageOpen(page: Page, changeAccount: () => Promise<void>): Promise<string[]> {
  await signIn(page.request, panelAccount('several'));
  await page.goto('/dashboard/businesses');
  await expect(firstBusiness(page)).toBeVisible();
  await settled(page);

  // The rows came through the stream, so the SDK knows the page had a session: a 401 now means it ended. Opening a
  // business changes the subscriptions, and the stream's reopening is the request that waits for its 401.
  const streamReopening = signal();
  const sessionEnded = signal();
  await page.route(STREAM, async (route) => {
    streamReopening.reach();
    await sessionEnded.reached;
    await route.fulfill(SESSION_ENDED);
  });
  await firstBusiness(page).locator('[data-testid$="-manage"]').click();
  await streamReopening.reached;

  let heldAsk: Route | undefined;
  const pageAsked = signal();
  await page.route(SESSION_API, async (route) => {
    if (heldAsk) return route.continue();
    heldAsk = route;
    pageAsked.reach();
  });

  let cookieItLeftWith = '';
  const post = page.request.post.bind(page.request);
  page.request.post = async (url, options) => {
    if (url === CONFIRM_CODE_API) {
      cookieItLeftWith = (await page.context().cookies()).find((cookie) => cookie.name === 'sessionid')?.value ?? '';
      sessionEnded.reach();
      if (page.url() !== 'about:blank') await pageAsked.reached;
    }
    return post(url, options);
  };
  await changeAccount();
  page.request.post = post;
  expect(cookieItLeftWith, 'the password step left its session in the cookies').not.toBe('');

  let setCookies: string[] = [];
  if (heldAsk) {
    const answer = await heldAsk.fetch({ headers: { ...heldAsk.request().headers(), cookie: `sessionid=${cookieItLeftWith}` } });
    setCookies = answer
      .headersArray()
      .filter(({ name }) => name.toLowerCase() === 'set-cookie')
      .map(({ value }) => value);
    await heldAsk.fulfill({ response: answer });
  }
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  return setCookies;
}

test('control: with the page left open, its late answer deletes the session of the next account', async ({ page }) => {
  const setCookies = await changeAccountWithAPageOpen(page, async () => {
    await page.context().clearCookies();
    await signIn(page.request, NEXT_ACCOUNT);
  });

  expect(setCookies).toContainEqual(expect.stringMatching(/^sessionid="";/));
  expect((await sessionOf(page.request)).user).toBeNull();
  await page.goto('/dashboard/businesses');
  await expect(page.getByTestId('login-form')).toBeVisible();
});

test('signInAs leaves the page first: the next account stays signed in', async ({ page }) => {
  await changeAccountWithAPageOpen(page, () => signInAs(page, NEXT_ACCOUNT));

  expect((await sessionOf(page.request)).user).toMatchObject({ email: NEXT_ACCOUNT.email });
  await page.goto('/dashboard/businesses');
  await expect(firstBusiness(page)).toBeVisible();
});
