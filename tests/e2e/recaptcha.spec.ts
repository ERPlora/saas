// reCAPTCHA Enterprise, invisible, on every public form (Ioan, 2026-10-22: «no se vea en la pantalla», «siempre que
// hay un form hay que meter recaptcha»), in a real browser against the production-like public server (its CSP, the
// SPA's Trusted Types): the contact form, the demo and the sign-in with its mailed code. Google is played in the
// browser by the fake enterprise.js of recaptcha.ts and on the server by the run's double (recaptcha-double.ts), so
// a refused form is a bot the spec chose. No checkbox, no puzzle: only the notice under the form; Google's badge is
// hidden. The last test loads Google's REAL script on localhost when the checkout has both keys in `.env` (the
// localhost site key and the API key): its token is made under the very same policies, and Google itself says the
// token is valid and made for that form (its score of a headless Chrome is not asserted).
import { readdirSync } from 'node:fs';

import { readMailCode } from '@erplora/ui/testing/mail';
import type { Page } from '@playwright/test';

import { OWNER, seedAccounts, submitSignInForm } from './panel/fixtures';
import { PUBLIC_MAIL_DIR } from './playwright.config';
import { expect, test } from './public-test';
import {
  askedAssessments,
  assessWithGoogle,
  E2E_RECAPTCHA_SITE_KEY,
  fakeGoogleRecaptcha,
  localRecaptchaApiKey,
  localRecaptchaSiteKey,
} from './recaptcha';
import { STACK } from './stack';

const SAAS_DIR = new URL('../..', import.meta.url).pathname;
const UNVERIFIED = 'We could not check that you are a person. Try again.';

/** Every CSP violation, Trusted Types refusal and page error, however the browser reports it (as public-web.spec.ts). */
async function watch(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (message) => {
    if (/content security policy|trusted ?type|refused to/i.test(message.text())) consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) => w.__csp.push(`${event.violatedDirective} ${event.blockedURI}`));
  });
  return async (where: string) => {
    const violations = await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
    expect({ violations, consoleErrors, pageErrors }, where).toEqual({ violations: [], consoleErrors: [], pageErrors: [] });
  };
}

/** How many mails the public server wrote so far. */
function mailCount(): number {
  try {
    return readdirSync(PUBLIC_MAIL_DIR).length;
  } catch {
    return 0;
  }
}

async function sendContactMessage(page: Page): Promise<void> {
  for (const [name, value] of [
    ['first_name', 'Anne'],
    ['last_name', 'Garcia'],
    ['email', 'anne@example.com'],
    ['message', 'Is there a demo for hair salons?'],
  ]) {
    await page.locator(`#contact-form [name="${name}"] :is(input, textarea)`).fill(value);
  }
  await page.locator('#contact-form ion-button[type="submit"]').click();
}

/** The assessments the double was asked from now on. */
async function assessmentsSince(): Promise<() => Promise<Array<{ token: string; expectedAction: string }>>> {
  const before = (await askedAssessments(STACK)).length;
  return async () => (await askedAssessments(STACK)).slice(before);
}

test.use({ locale: 'en-GB' });

test('the contact form asks Google without a word to the visitor, and the message is sent', async ({ page }) => {
  const clean = await watch(page);
  const asked = await assessmentsSince();
  const mails = mailCount();
  await page.goto('/contact/');

  await expect(page.getByTestId('recaptcha-notice')).toContainText('This site is protected by reCAPTCHA');
  await expect(page.locator('.grecaptcha-badge')).toBeHidden();
  await sendContactMessage(page);

  await expect(page.locator('ion-toast')).toContainText('business hour');
  expect(await asked()).toEqual([{ token: 'e2e-human:contact', expectedAction: 'contact' }]);
  await expect.poll(mailCount).toBe(mails + 1);
  await clean('/contact/');
});

for (const [kind, why] of [
  ['bot', 'Google scores a bot'],
  ['blocked', 'Google is blocked (an extension)'],
] as const) {
  test(`the contact form is not sent when ${why}, and the visitor is told`, async ({ page, context }) => {
    await fakeGoogleRecaptcha(context, kind);
    const mails = mailCount();
    await page.goto('/contact/');

    await sendContactMessage(page);

    await expect(page.locator('ion-toast')).toContainText(UNVERIFIED);
    await expect(page.locator('#contact-form [name="first_name"] input')).toHaveValue('Anne');
    expect(mailCount()).toBe(mails);
  });
}

test('the demo asks Google before the Hub: a bot is told, a person goes on to the Hub', async ({ page, context }) => {
  const clean = await watch(page);
  await fakeGoogleRecaptcha(context, 'bot');
  await page.goto('/demo/');
  await expect(page.getByTestId('recaptcha-notice')).toBeVisible();

  await page.getByTestId('demo-start').click();

  await expect(page.getByTestId('demo-state-unverified')).toContainText(UNVERIFIED);
  await fakeGoogleRecaptcha(context, 'human');
  const asked = await assessmentsSince();
  await page.reload();
  await page.getByTestId('demo-start').click();
  // This server has no Hub (demo-door.spec.ts): past reCAPTCHA, the Hub is away.
  await expect(page.getByTestId('demo-state-unavailable')).toBeVisible();
  expect(await asked()).toEqual([{ token: 'e2e-human:demo_request', expectedAction: 'demo_request' }]);
  await clean('/demo/');
});

test.describe('the sign-in, under the SPA’s CSP and Trusted Types', () => {
  test.beforeAll(() => seedAccounts());

  test('signs in with the password and the mailed code, each with its own token', async ({ page }) => {
    const clean = await watch(page);
    const asked = await assessmentsSince();
    await page.goto('/launch');
    await expect(page.getByTestId('recaptcha-notice')).toContainText('This site is protected by reCAPTCHA');
    await expect(page.locator('.grecaptcha-badge')).toBeHidden();

    const since = Date.now();
    await submitSignInForm(page, OWNER);
    await expect(page).toHaveURL(/\/verify-email(\?|$)/);
    const code = await readMailCode({ dir: PUBLIC_MAIL_DIR, to: OWNER.email, since });
    await page.getByTestId('code').locator('input').fill(code);
    await page.getByTestId('verify-email-submit').click();

    await expect(page).not.toHaveURL(/\/verify-email(\?|$)/);
    expect(await asked()).toEqual([
      { token: 'e2e-human:login', expectedAction: 'login' },
      { token: 'e2e-human:login_code', expectedAction: 'login_code' },
    ]);
    await clean('/launch');
  });

  test('a bot is told under the form and goes nowhere', async ({ page, context }) => {
    await fakeGoogleRecaptcha(context, 'bot');
    await page.goto('/launch');

    await submitSignInForm(page, OWNER);

    await expect(page.locator('.non-field-error')).toHaveText(UNVERIFIED);
    await expect(page).toHaveURL(/\/launch(\?|$)/);
  });
});

test.describe('with Google’s real script', () => {
  const siteKey = localRecaptchaSiteKey(SAAS_DIR);
  const apiKey = localRecaptchaApiKey(SAAS_DIR);
  // Google is called only with both keys of a checkout that asked for it (encargo W16): the network and Google itself.
  test.skip(!siteKey || siteKey === E2E_RECAPTCHA_SITE_KEY || !apiKey, 'needs RECAPTCHA_SITE_KEY and RECAPTCHA_API_KEY in .env');

  /** The body the page will post to `path`, held there: Google's real token never reaches the double. (In an object:
   *  an async function that returned the promise itself would wait for the post.) */
  async function heldPost(page: Page, path: string): Promise<{ body: Promise<Record<string, string>> }> {
    let posted!: (body: Record<string, string>) => void;
    const body = new Promise<Record<string, string>>((resolve) => (posted = resolve));
    await page.route(`**${path}`, async (route) => {
      const raw = route.request().postData() ?? '';
      posted(raw.startsWith('{') ? (JSON.parse(raw) as Record<string, string>) : Object.fromEntries(new URLSearchParams(raw)));
      await route.fulfill({ status: 400, contentType: 'application/json', body: '{"status": 400, "errors": []}' });
    });
    return { body };
  }

  test('makes a token on the sign-in (SPA) and on the contact form (public web) without breaking a policy', async ({ page, context }) => {
    await context.unrouteAll({ behavior: 'ignoreErrors' });
    const clean = await watch(page);
    const origin = `http://localhost:${STACK.publicPort}`;

    const login = await heldPost(page, '/_allauth/browser/v1/auth/login');
    await page.goto(`${origin}/launch`);
    await submitSignInForm(page, OWNER);
    const { recaptcha_token: loginToken } = await login.body;
    expect(loginToken.length, 'Google’s token of `login`').toBeGreaterThan(100);
    expect(loginToken.startsWith('e2e-')).toBe(false);
    await clean('/launch with Google');
    const verdict = await assessWithGoogle({ token: loginToken, action: 'login', siteKey, apiKey });
    // A valid token still carries `invalidReason: INVALID_REASON_UNSPECIFIED` (the enum's default).
    expect([verdict.valid, verdict.action], 'Google’s verdict on the `login` token').toEqual([true, 'login']);
    test.info().annotations.push({ type: 'google-score', description: `login: ${verdict.score}` });

    const contact = await heldPost(page, '/contact/submit/');
    await page.goto(`${origin}/contact/`);
    await sendContactMessage(page);
    const { recaptcha_token: contactToken } = await contact.body;
    expect(contactToken.length, 'Google’s token of `contact`').toBeGreaterThan(100);
    await expect(page.locator('.grecaptcha-badge')).toBeHidden();
    await clean('/contact/ with Google');
  });
});
