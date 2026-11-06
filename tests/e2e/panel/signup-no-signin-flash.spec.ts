// flow: ACCOUNTS-F01
// «Create account» goes straight to «Check your email» (ACCOUNTS-F01 step 4): the leaving form never turns into «Sign in»
// on its way out (saas#291). Ionic animates the launcher out, and keeps it in its stack, once the address is already the
// code page's, which has no `?tab=` and no `?notice=`: the form used to follow that address and paint «Sign in» and
// «Forgot your password?» for a frame or two, and to drop its notice (the expired code's, ACCOUNTS-F02) under the
// leaving form. A recorder in the page writes down every form's tab and button, the links and the notices at each
// change of the page, from the click until the code page is on screen and still, in both languages at the three sizes.
// Accounts of this spec: `e2e-signup-flash-…@example.com`, removed before and after.
import { type Page } from '@playwright/test';

import {
  captureAtEverySize,
  type Credentials,
  expect,
  provenAccount,
  removeAccountsOf,
  settled,
  submitSignInForm,
  test,
  type Viewport,
  VIEWPORTS,
  watchPageErrors,
} from './fixtures';
import { LANGUAGES, t } from './language-review';

const PREFIX = 'e2e-signup-flash-';
const PASSWORD = 'Signup-e2e-2026!';

/** What the page shows of the sign-in form at one change of the page. */
interface FormState {
  /** `<tab> · <button>` of every form in the page, the leaving one included. */
  forms: string[];
  /** «Forgot your password?» links in the page: «Sign in» only. */
  forgot: number;
  /** Notices of the form in the page (`?notice=`). */
  notices: number;
  /** The code page is in the page. */
  code: boolean;
}

/** Starts writing down, in the page, what the form shows now and at every change of the page (each new state once). */
async function recordForm(page: Page): Promise<void> {
  await page.evaluate(() => {
    const states: FormState[] = [];
    const read = () => {
      const state: FormState = {
        forms: [...document.querySelectorAll<HTMLElement & { value?: unknown }>('[data-testid="login-tabs"]')].map((tabs) => {
          const button = tabs.parentElement?.querySelector('[data-testid="login-submit"]');
          return `${String(tabs.value)} · ${button?.textContent?.trim() ?? ''}`;
        }),
        forgot: document.querySelectorAll('[data-testid="login-forgot"]').length,
        notices: document.querySelectorAll('[data-testid="login-notice"]').length,
        code: document.querySelector('[data-testid="verify-email-form"]') !== null,
      };
      if (JSON.stringify(state) !== JSON.stringify(states.at(-1))) states.push(state);
    };
    read();
    new MutationObserver(read).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    (window as unknown as { formStates: FormState[] }).formStates = states;
  });
}

const walk = captureAtEverySize('SAAS-291');

/**
 * At each size (`captureAtEverySize`), from a fresh visit to `start`: submits `credentials(size)` and waits for the code
 * page, on screen and still. Returns, per size, what the form showed from the click on: the forms (`<tab> · <button>`,
 * each once), the most «Forgot your password?» links and the fewest notices at once. Every size leaves a capture of the
 * code page, `SAAS-291-<name>-<size>`.
 */
async function leaveForTheCode(page: Page, name: string, start: string, credentials: (size: string) => Credentials) {
  const seen: Record<string, { forms: string[]; forgot: number; notices: number }> = {};
  const ready = async (size: Viewport) => {
    await page.context().clearCookies();
    await page.goto(start);
    await expect(page.getByTestId('login-form')).toBeVisible();
    await settled(page);
    await recordForm(page);

    await submitSignInForm(page, credentials(String(size.width)));
    await expect(page).toHaveURL(/\/verify-email$/);
    await expect(page.getByTestId('verify-email-form')).toBeVisible();
  };
  const checks = async (size: Viewport) => {
    const states = await page.evaluate(() => (window as unknown as { formStates: FormState[] }).formStates);
    expect(states.some((state) => state.code), `the recorder saw the code page arrive at ${size.width}`).toBe(true);
    seen[size.width] = {
      forms: [...new Set(states.flatMap((state) => state.forms))],
      forgot: Math.max(...states.map((state) => state.forgot)),
      notices: Math.min(...states.map((state) => state.notices)),
    };
  };
  await walk(page, name, ready, { checks });
  return seen;
}

/** The same `value` at every size of the panel. */
const atEverySize = <T>(value: T): Record<string, T> => Object.fromEntries(VIEWPORTS.map((size) => [size.width, value]));

test.beforeAll(() => removeAccountsOf(PREFIX));
test.afterAll(() => removeAccountsOf(PREFIX));

for (const { lang, locale } of LANGUAGES) {
  test.describe(`with the page in ${lang}`, () => {
    test.use({ locale });

    test(`ACCOUNTS-F01: «Create account» goes straight to the code page, never through «Sign in», in ${lang} (saas#291)`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const seen = await leaveForTheCode(page, `signup-${lang}`, '/launch?tab=signup', (size) => ({
        email: `${PREFIX}new-${lang}-${size}-${Date.now()}@example.com`,
        password: PASSWORD,
      }));
      expect(seen).toEqual(atEverySize({ forms: [`signup · ${t(lang, 'accounts.login.signUp')}`], forgot: 0, notices: 0 }));
      expect(errors).toEqual([]);
    });

    test(`ACCOUNTS-F02: signing in again after an expired code keeps its notice on the way to the new code, in ${lang} (saas#291)`, async ({
      page,
    }) => {
      const errors = watchPageErrors(page);
      const account = { email: `${PREFIX}known-${lang}-${Date.now()}@example.com`, password: PASSWORD };
      provenAccount(account.email, account.password, lang);
      const seen = await leaveForTheCode(page, `notice-${lang}`, '/launch?notice=code_expired', () => account);
      expect(seen).toEqual(atEverySize({ forms: [`signin · ${t(lang, 'accounts.login.signIn')}`], forgot: 1, notices: 1 }));
      expect(errors).toEqual([]);
    });
  });
}
