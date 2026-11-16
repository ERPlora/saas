import { type APIRequestContext, type APIResponse, expect, type Page } from '@playwright/test';

import type { Credentials } from './accounts';
import { waitForMailCode } from './mail';

/** allauth.headless's sign-in for the browser client: what the launcher's form posts. */
const SIGN_IN_API = '/_allauth/browser/v1/auth/login';
/** The second step of every password sign-in: the code mailed to the account (what /verify-email posts). */
export const CONFIRM_CODE_API = '/_allauth/browser/v1/auth/code/confirm';

/** What `GET /api/me` (`base.session.me`) answers: `user` is null without a session. */
export interface Session {
  user: { id: string; label: string } | null;
  scope: { kind: string; key: string };
}

/** The session behind `request` (a page's or a context's: they share its cookies). */
export async function sessionOf(request: APIRequestContext): Promise<Session> {
  const response = await request.get('/api/me');
  expect(response.status(), 'GET /api/me').toBe(200);
  return (await response.json()) as Session;
}

/** The CSRF token of `request`'s cookies (the SPA's HTML sets it; a sign-in rotates it). */
async function csrfOf(request: APIRequestContext): Promise<string> {
  const { cookies } = await request.storageState();
  const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value;
  if (!csrf) throw new Error('no csrftoken cookie: load a page of the SPA first');
  return csrf;
}

/**
 * Signs `request`'s browser context in through allauth.headless, as the launcher's form and /verify-email
 * do: the SPA's HTML sets Django's CSRF cookie (`live.spa`, `ensure_csrf_cookie`) and the API wants it back
 * in `X-CSRFToken`; the password waits for the code mailed to the account (`login_by_code`), read from the
 * panel's mail folder (the newest to that address since the password was posted) and confirmed. The session
 * cookie lands in the context, so its pages are signed in.
 */
export async function signIn(request: APIRequestContext, credentials: Credentials): Promise<void> {
  const launcher = await request.get('/launch');
  expect(launcher.status(), 'GET /launch').toBe(200);
  const csrf = await csrfOf(request);
  const since = Date.now();
  const password = await request.post(SIGN_IN_API, { headers: { 'X-CSRFToken': csrf }, data: credentials });
  const waiting = (await password.json()) as { data?: { flows?: Array<{ id: string; is_pending?: boolean }> } };
  const pending = waiting.data?.flows?.filter((flow) => flow.is_pending).map((flow) => flow.id);
  expect([password.status(), pending], `POST ${SIGN_IN_API}: ${JSON.stringify(waiting)}`).toEqual([401, ['login_by_code']]);
  const code = await waitForMailCode(credentials.email, since);
  const confirmed = await request.post(CONFIRM_CODE_API, { headers: { 'X-CSRFToken': csrf }, data: { code } });
  expect(confirmed.status(), `POST ${CONFIRM_CODE_API}: ${await confirmed.text()}`).toBe(200);
}

/**
 * Signs the page's context in as `credentials`, signing out whoever was in (allauth refuses a second sign-in: 409).
 * The page leaves first: left open, it sees its session end, reloads and asks for it again, and an answer that comes
 * after the code to a request that carried the password step's cookie deletes the new session's
 * (panel/sign-in-as.spec.ts).
 */
export async function signInAs(page: Page, credentials: Credentials): Promise<void> {
  await page.goto('about:blank');
  await page.context().clearCookies();
  await signIn(page.request, credentials);
}

/**
 * The launcher's form, already on screen: types `credentials` and submits. The page then goes to
 * /verify-email for the mailed code (or leaves, signed in, when no code is asked).
 */
export async function submitSignInForm(page: Page, credentials: Credentials): Promise<void> {
  const form = page.getByTestId('login-form');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  await form.getByTestId('login-submit').click();
}

/**
 * The real sign-in, on the launcher's form already on screen: the password, then the code mailed to the
 * account, typed on /verify-email as the person does. The page then leaves for its `next` (or the
 * launcher) with a full load.
 */
export async function signInThroughPage(page: Page, credentials: Credentials): Promise<void> {
  const since = Date.now();
  await submitSignInForm(page, credentials);
  await expect(page).toHaveURL(/\/verify-email(\?|$)/);
  const code = await waitForMailCode(credentials.email, since);
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).not.toHaveURL(/\/verify-email(\?|$)/);
}

/**
 * A POST to the panel's API as `request`'s account, with Django's CSRF token from its cookies (set
 * by the SPA's HTML, so after `signIn` or a page load).
 */
export async function apiPost(request: APIRequestContext, path: string, data: unknown): Promise<APIResponse> {
  const { cookies } = await request.storageState();
  const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value;
  if (!csrf) throw new Error(`POST ${path}: no csrftoken cookie (sign in first)`);
  return request.post(path, { headers: { 'X-CSRFToken': csrf }, data });
}
