// flow: ACCOUNTS-F06
// «Continue with Google» (accounts/WORKBOOK.md, ACCOUNTS-F06) at the three sizes, on the panel's
// twin with a made-up Google app (`GOOGLE_E2E`, panel/project.ts), because the flow hands over to the second factor.
// Everything of ours is the real thing: the button, the form post, allauth.headless's redirect with its state and
// its PKCE, the page's `form-action` over that redirect, the way back, allauth's exchange of the code, the account,
// the session and the mails. Only Google is played, in its two halves:
//   - what the browser sees at accounts.google.com: the DevTools protocol (`Fetch`, Chrome's own) answers with a page
//     to accept or cancel on, and the two links are the ways back Google redirects to. Not `page.route`, which is
//     only called for the first address of a redirect: the browser would reach the real Google. Here the browser still
//     checks the page's `form-action` over the redirect, before anything is answered;
//   - what the server asks at its token endpoint: the double of this spec (`GOOGLE_OAUTH_TOKEN_URL`, which only a
//     development server may move, config/tests/test_production_settings.py), which answers each code with the
//     id_token of the account chosen.
// No run needs a credential of Google or calls it. Accounts of this spec: `e2e-google-…@example.com`, removed before
// and after (panel_seed.py's `clear` removes every `e2e-…@example.com` too).
import { createHash } from 'node:crypto';
import { createServer, type Server } from 'node:http';

import { type Page } from '@playwright/test';

import {
  createAccountWarm,
  djangoPrintWarm,
  expect,
  removeAccountsWarm,
  sessionOf,
  settled,
  shot,
  sidewaysScroll,
  test,
  VIEWPORTS,
  waitForMail,
  watchPageErrors,
} from './fixtures';
import { GOOGLE_E2E, PANEL_MFA_URL } from './project';
import { STACK } from '../stack';

const PREFIX = 'e2e-google-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const SECURITY = '/dashboard/account/security';

/** A fresh address of this spec, never used before. */
const address = (name: string, size: number): string => `${PREFIX}${name}-${size}-${Date.now()}@example.com`;

const removeAccounts = () => removeAccountsWarm(PREFIX);

// ── Google's token endpoint, as the panel's Django calls it ───────────────────────────────────

/** The id_token's claims Google hands back for one of its accounts. */
interface GoogleAccount {
  sub: string;
  email: string;
  email_verified: boolean;
}

const base64url = (text: string): string => Buffer.from(text).toString('base64url');

/** An id_token of `account`. allauth reads it from its own call to the endpoint, so it checks no signature. */
function idToken(account: GoogleAccount): string {
  const now = Math.floor(Date.now() / 1000);
  const claims = { iss: 'https://accounts.google.com', aud: GOOGLE_E2E.clientId, iat: now, exp: now + 3600, ...account };
  return [base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' })), base64url(JSON.stringify(claims)), base64url('unsigned')].join('.');
}

const accepted = new Map<string, GoogleAccount>();
const exchanges: Record<string, string>[] = [];
let tokenEndpoint: Server;

async function startTokenEndpoint(): Promise<void> {
  tokenEndpoint = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on('data', (chunk: Buffer) => chunks.push(chunk));
    request.on('end', () => {
      const sent = Object.fromEntries(new URLSearchParams(Buffer.concat(chunks).toString('utf8')));
      exchanges.push(sent);
      const account = accepted.get(sent.code ?? '');
      response.writeHead(account ? 200 : 400, { 'Content-Type': 'application/json' });
      response.end(
        JSON.stringify(
          account ? { access_token: 'e2e-access-token', expires_in: 3599, id_token: idToken(account) } : { error: 'invalid_grant' },
        ),
      );
    });
  });
  await new Promise<void>((listening, failed) => {
    tokenEndpoint.once('error', failed);
    tokenEndpoint.listen(STACK.googleDoublePort, '127.0.0.1', () => listening());
  });
}

// ── Google's screens, as the browser sees them ────────────────────────────────────────────────

/** The title of the screen below: never the real Google's, so a run that reached Google fails on it. */
const PLAYED_GOOGLE = 'Google, played by the e2e';

interface PlayedGoogle {
  /** What left for Google, once the browser has gone there. */
  authorization(): URL;
  /** Stops playing it, for a second account in the same test. */
  stop(): Promise<void>;
}

/** Plays Google's screens for `page`, where `account` is the one accepted. */
async function playGoogle(page: Page, account: GoogleAccount): Promise<PlayedGoogle> {
  const code = `4/e2e-${account.sub}-${Date.now()}`;
  accepted.set(code, account);
  let last: URL | undefined;
  const devtools = await page.context().newCDPSession(page);
  devtools.on('Fetch.requestPaused', ({ requestId, request }) => {
    const asked = new URL(request.url);
    // Whatever else the browser asks there (its favicon) does not reach Google either.
    if (!asked.pathname.startsWith('/o/oauth2/')) {
      void devtools.send('Fetch.fulfillRequest', { requestId, responseCode: 404 });
      return;
    }
    last = asked;
    const back = (answer: Record<string, string>): string => {
      const url = new URL(asked.searchParams.get('redirect_uri') ?? '');
      url.search = new URLSearchParams({ state: asked.searchParams.get('state') ?? '', ...answer }).toString();
      return url.toString();
    };
    const screen = `<!doctype html><title>${PLAYED_GOOGLE}</title>
      <a id="accept" href="${back({ code })}">Accept</a>
      <a id="cancel" href="${back({ error: 'access_denied' })}">Cancel</a>`;
    void devtools.send('Fetch.fulfillRequest', {
      requestId,
      responseCode: 200,
      responseHeaders: [{ name: 'Content-Type', value: 'text/html' }],
      body: Buffer.from(screen).toString('base64'),
    });
  });
  await devtools.send('Fetch.enable', { patterns: [{ urlPattern: 'https://accounts.google.com/*' }] });
  return {
    authorization() {
      if (!last) throw new Error('the browser never went to Google');
      return last;
    },
    stop: () => devtools.detach(),
  };
}

// ── What the account ended up with ────────────────────────────────────────────────────────────

interface AccountState {
  id: string;
  usablePassword: boolean;
  addressVerified: boolean;
  googleUid: string | null;
  termsAccepted: boolean;
}

async function accountOf(email: string): Promise<AccountState | null> {
  const state = await djangoPrintWarm(
    [
      'import json',
      'from allauth.account.models import EmailAddress',
      'from allauth.socialaccount.models import SocialAccount',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.filter(email=${JSON.stringify(email)}).first()`,
      'link = user and SocialAccount.objects.filter(user=user, provider="google").first()',
      'print(json.dumps(user and {',
      '  "id": str(user.pk),',
      '  "usablePassword": user.has_usable_password(),',
      '  "addressVerified": EmailAddress.objects.filter(user=user, email=user.email, verified=True).exists(),',
      '  "googleUid": link.uid if link else None,',
      '  "termsAccepted": user.terms_accepted_at is not None,',
      '}))',
    ].join('\n'),
  );
  return JSON.parse(state) as AccountState | null;
}

/** An account of erplora.com with `email` confirmed and a password, not linked to any Google. */
const createAccount = (email: string) => createAccountWarm(email, PASSWORD);

/** That account with the authenticator app on: its key. */
function turnOnTheApp(email: string): Promise<string> {
  return djangoPrintWarm(
    [
      'from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret',
      'from django.contrib.auth import get_user_model',
      'secret = generate_totp_secret()',
      `TOTP.activate(get_user_model().objects.get(email=${JSON.stringify(email)}), secret)`,
      'print(secret)',
    ].join('\n'),
  );
}

/** The code the app shows now for `secret`. */
function appCode(secret: string): Promise<string> {
  return djangoPrintWarm(
    [
      'import time',
      'from allauth.mfa import app_settings',
      'from allauth.mfa.totp.internal.auth import format_hotp_value, hotp_value',
      `print(format_hotp_value(hotp_value(${JSON.stringify(secret)}, int(time.time()) // app_settings.TOTP_PERIOD)))`,
    ].join('\n'),
  );
}

/**
 * The launcher of an account with no business, loaded: the form that creates the first one and «Go to the panel».
 * `settled` waits for nothing here, because it leaves endless spinners aside: the page would be read while it loads.
 */
async function expectFirstBusinessForm(page: Page): Promise<void> {
  await expect(page.getByTestId('launch-panel')).toBeVisible();
  await expect(page.getByTestId('create-name')).toBeVisible();
  await expect(page.getByTestId('create-submit')).toBeVisible();
  await expect(page.getByTestId('launch-loading')).toHaveCount(0);
  await expect(page.getByTestId('launch-error')).toHaveCount(0);
}

// ── The flow ──────────────────────────────────────────────────────────────────────────────────

test.use({ baseURL: PANEL_MFA_URL });

test.beforeAll(async () => {
  await removeAccounts();
  await startTokenEndpoint();
});

test.afterAll(async () => {
  await new Promise<void>((closed) => {
    tokenEndpoint.closeAllConnections();
    tokenEndpoint.close(() => closed());
  });
  await removeAccounts();
});

for (const size of VIEWPORTS) {
  test.describe(`at ${size.width}`, () => {
    test.use({ viewport: { width: size.width, height: size.height } });

    /** The button on the sign-in, no sideways scroll, and the click that leaves for Google. */
    async function continueWithGoogle(page: Page, capture?: string): Promise<void> {
      const form = page.getByTestId('login-google');
      await expect(form).toContainText('Continue with Google');
      await settled(page);
      expect(await sidewaysScroll(page), `the sign-in scrolls sideways at ${size.width}`).toEqual([]);
      if (capture) await page.screenshot({ path: shot(`CLOSE-ACCOUNTS-F06-${capture}-${size.width}`), fullPage: true });
      await form.locator('ion-button').click();
      await expect(page).toHaveTitle(PLAYED_GOOGLE);
    }

    test(`ACCOUNTS-F06 an address with no account gets one, confirmed and with no form, and lands on the launcher (${size.width})`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const email = address('new', size.width);
      const account = { sub: `new-${size.width}-${Date.now()}`, email, email_verified: true };
      const google = await playGoogle(page, account);

      await page.goto('/launch');
      await continueWithGoogle(page, 'sign-in');
      await page.locator('#accept').click();

      await expect(page).toHaveURL(/\/launch$/);
      await expect(page.getByTestId('login-google')).toHaveCount(0);
      await expectFirstBusinessForm(page);
      await settled(page);
      expect(await sidewaysScroll(page), `the launcher scrolls sideways at ${size.width}`).toEqual([]);
      await page.screenshot({ path: shot(`CLOSE-ACCOUNTS-F06-new-account-${size.width}`), fullPage: true });

      const created = await accountOf(email);
      expect(created).toMatchObject({
        usablePassword: false,
        addressVerified: true,
        googleUid: account.sub,
        termsAccepted: true,
      });
      expect((await sessionOf(page.request)).user?.id).toBe(created?.id);

      // The authorization carries our state and PKCE, and the server proves them when it exchanges the code.
      const sent = google.authorization().searchParams;
      expect(sent.get('client_id')).toBe(GOOGLE_E2E.clientId);
      expect(sent.get('code_challenge_method')).toBe('S256');
      const exchange = exchanges.at(-1) ?? {};
      expect(exchange.client_secret).toBe(GOOGLE_E2E.clientSecret);
      expect(exchange.redirect_uri).toBe(`${PANEL_MFA_URL}/auth/google/callback/`);
      expect(createHash('sha256').update(exchange.code_verifier ?? '').digest('base64url')).toBe(sent.get('code_challenge'));
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F06 the address of an account signs in to it, links Google, tells the owner and goes where it was going (${size.width})`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const email = address('known', size.width);
      await createAccount(email);
      const before = await accountOf(email);
      const account = { sub: `known-${size.width}-${Date.now()}`, email, email_verified: true };
      await playGoogle(page, account);
      const since = Date.now();

      await page.goto(`/launch?next=${encodeURIComponent(SECURITY)}`);
      await continueWithGoogle(page);
      await page.locator('#accept').click();

      await expect(page).toHaveURL(new RegExp(`${SECURITY}$`));
      await expect(page.getByTestId('google-row')).toContainText(email);
      await settled(page);
      expect(await sidewaysScroll(page), `Security scrolls sideways at ${size.width}`).toEqual([]);
      await page.screenshot({ path: shot(`CLOSE-ACCOUNTS-F06-linked-${size.width}`), fullPage: true });

      const linked = await accountOf(email);
      expect(linked).toEqual({ ...before, googleUid: account.sub, termsAccepted: true });
      expect(linked?.usablePassword).toBe(true);
      expect((await sessionOf(page.request)).user?.id).toBe(before?.id);
      await waitForMail(email, since, /you can also sign in to your account with Google/);
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F06 with the authenticator app, the code comes first, and only then the session (${size.width})`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const email = address('app', size.width);
      await createAccount(email);
      const secret = await turnOnTheApp(email);
      await playGoogle(page, { sub: `app-${size.width}-${Date.now()}`, email, email_verified: true });

      await page.goto('/launch');
      await continueWithGoogle(page);
      await page.locator('#accept').click();

      await expect(page).toHaveURL(/\/2fa\/authenticate(\?|$)/);
      await expect(page.getByTestId('mfa-form')).toBeVisible();
      await settled(page);
      expect(await sidewaysScroll(page), `the code scrolls sideways at ${size.width}`).toEqual([]);
      await page.screenshot({ path: shot(`CLOSE-ACCOUNTS-F06-authenticator-${size.width}`), fullPage: true });
      expect((await sessionOf(page.request)).user).toBeNull();

      await page.getByTestId('code').locator('input').fill(await appCode(secret));
      await page.getByTestId('mfa-submit').click();

      await expect(page).toHaveURL(/\/launch$/);
      await expectFirstBusinessForm(page);
      expect((await sessionOf(page.request)).user?.id).toBe((await accountOf(email))?.id);
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F06 «Cancel» at Google goes back to the sign-in, keeping where it was going, with nothing created (${size.width})`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const email = address('cancel', size.width);
      await playGoogle(page, { sub: `cancel-${size.width}`, email, email_verified: true });

      await page.goto(`/launch?next=${encodeURIComponent(SECURITY)}`);
      await continueWithGoogle(page);
      await page.locator('#cancel').click();

      await expect(page).toHaveURL(new RegExp(`/launch\\?next=${SECURITY}$`));
      await expect(page.getByTestId('login-google')).toBeVisible();
      await settled(page);
      expect(await sidewaysScroll(page), `the sign-in scrolls sideways at ${size.width}`).toEqual([]);
      expect((await sessionOf(page.request)).user).toBeNull();
      expect(await accountOf(email)).toBeNull();
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F06 an address Google does not vouch for ends on the error page, with nothing created nor linked (${size.width})`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const stranger = address('unverified', size.width);
      const owner = address('owner', size.width);
      await createAccount(owner);

      for (const email of [stranger, owner]) {
        await page.context().clearCookies();
        const google = await playGoogle(page, { sub: `unverified-${size.width}-${Date.now()}`, email, email_verified: false });

        await page.goto('/launch');
        await continueWithGoogle(page);
        await page.locator('#accept').click();

        await expect(page).toHaveURL(/\/login\/error\?code=authentication_error/);
        await expect(page.getByRole('heading', { name: 'We could not sign you in with Google' })).toBeVisible();
        await settled(page);
        expect(await sidewaysScroll(page), `the error page scrolls sideways at ${size.width}`).toEqual([]);
        expect((await sessionOf(page.request)).user).toBeNull();
        await google.stop();
      }
      await page.screenshot({ path: shot(`CLOSE-ACCOUNTS-F06-error-${size.width}`), fullPage: true });

      expect(await accountOf(stranger)).toBeNull();
      expect((await accountOf(owner))?.googleUid).toBeNull();

      await page.getByTestId('login-error-action').click();
      await expect(page).toHaveURL(/\/launch(\?|$)/);
      await expect(page.getByTestId('login-google')).toBeVisible();
      expect(errors).toEqual([]);
    });
  });
}
