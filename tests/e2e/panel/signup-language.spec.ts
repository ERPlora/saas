// flow: ACCOUNTS-F01
// Whoever signs up keeps the language of the page (ACCOUNTS-F01, ACCOUNTS-F22, HUBS-F01): the real sign-up on the
// launcher, the mailed code, «Create your business» in that language with no stop at Preferences, the business born
// in it (the row and what the Hub is told) and its «is ready» mail. Preferences still decides afterwards.
//
// The language comes from the browser (`locale` sends it as `Accept-Language`, as a real one does), never from a seed.
// Two parts, as panel/hubs-flows.spec.ts: the spec plays the Hub (`startHubDouble`) and reports the business ready, and
// «the real Hub» (`E2E_REAL_HUB=1`, README «El Hub real de la e2e»), where the business itself opens in the language.
// Accounts of this spec: `e2e-signup-lang-…@example.com`, removed before and after, with their businesses.
//
// No Python inside a test: each one boots Django cold and, run with `djangoPrint`, blocks this process until it ends.
// With the machine loaded that took 57 s and 88 s and the test's whole budget, charged to the next `await` (saas#346).
// What the panel shows is read through its API; what only Django knows, once for the spec, before its tests.
import { type APIRequestContext, type Page } from '@playwright/test';

import {
  businessIdOf,
  djangoPrintAsync,
  expect,
  type HubDouble,
  removeAccountsOf,
  reportBusinessReady,
  shot,
  startHubDouble,
  submitSignInForm,
  test,
  waitForMail,
  waitForMailCode,
  watchPageErrors,
} from './fixtures';
import { type Lang, LANGUAGES, reviewOf, t, textsOfTheOtherLanguage } from './language-review';
import { HUB_DOUBLE_PORT } from './project';

const PREFIX = 'e2e-signup-lang-';
const PASSWORD = 'Signup-e2e-2026!';
const review = reviewOf('SIGNUP-LANGUAGE');

/** The JSON the panel's API answers to `GET path` for `request`'s account. */
async function read(request: APIRequestContext, path: string): Promise<unknown> {
  const response = await request.get(path);
  if (!response.ok()) throw new Error(`GET ${path}: ${response.status()} ${await response.text()}`);
  return response.json();
}

/**
 * What the SaaS keeps for `request`'s account, as the panel reads it: the account's language (Preferences,
 * `user.language`), then that of each of its businesses (a business's settings, `hub.language`).
 */
async function languagesOf(request: APIRequestContext): Promise<string[]> {
  const account = (await read(request, '/api/accounts/preferences')) as { language: string };
  const { rows } = (await read(request, '/api/hubs/businesses?limit=50&offset=0')) as { rows: Array<{ id: string }> };
  const businesses = await Promise.all(rows.map(({ id }) => read(request, `/api/hubs/businesses/detail?id=${id}`)));
  return [account.language, ...(businesses as Array<{ language: string }>).map((business) => business.language)];
}

/** The first line of the «is ready» mail in each language, `%(business)s` unfilled: Django's own catalogue. */
let readyLines: Record<Lang, string>;

/** The first line of the «is ready» mail of `business` in `lang`. */
function readyLine(lang: Lang, business: string): string {
  return readyLines[lang].split('%(business)s').join(business);
}

const asPattern = (text: string) => new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));

/** The launcher's «Create account», on a browser in `lang`: the form, the mailed code and the launcher, signed in. */
async function signUp(page: Page, lang: Lang, name: string): Promise<string> {
  const email = `${PREFIX}${name}-${Date.now()}@example.com`;
  await page.goto('/launch?tab=signup');
  await expect(page.getByTestId('login-submit')).toHaveText(t(lang, 'accounts.login.signUp'));
  const since = Date.now();
  await submitSignInForm(page, { email, password: PASSWORD });
  await expect(page).toHaveURL(/\/verify-email$/);
  await page.getByTestId('code').locator('input').fill(await waitForMailCode(email, since));
  await page.getByTestId('verify-email-submit').click();
  await expect(page).toHaveURL(/\/launch$/);
  return email;
}

/** «Create your business», already on screen in `lang`: its form, down to «Preparing». */
async function createBusiness(page: Page, lang: Lang, name: string): Promise<string> {
  await expect(page.getByRole('heading', { name: t(lang, 'hubs.launch.first.title') })).toBeVisible();
  await page.getByTestId('create-name').locator('input').fill(name);
  await page.getByTestId('create-submit').click();
  await expect(page.getByRole('heading', { name, exact: false })).toBeVisible();
  return businessIdOf(page.request, name);
}

test.beforeAll(() => removeAccountsOf(PREFIX));
test.beforeAll(async () => {
  readyLines = JSON.parse(
    await djangoPrintAsync(
      [
        'import json',
        'from django.utils import translation',
        'from django.utils.translation import gettext',
        'lines = {}',
        `for lang in ${JSON.stringify(LANGUAGES.map(({ lang }) => lang))}:`,
        '    with translation.override(lang):',
        '        lines[lang] = gettext("%(business)s is ready: open it and start selling.")',
        'print(json.dumps(lines))',
      ].join('\n'),
    ),
  ) as Record<Lang, string>;
});
test.afterAll(() => removeAccountsOf(PREFIX));

test.describe('the spec plays the Hub', () => {
  test.skip(!!process.env.E2E_REAL_HUB, 'the real Hub takes the port of the double');

  let hub: HubDouble;
  test.beforeAll(async () => {
    hub = await startHubDouble();
  });
  test.afterAll(async () => {
    await hub.close();
  });

  /** The language the Hub was told for the business `id`: its registry (`PUT /internal/hubs/{id}`, `hub_client.put_hub`). */
  async function languageTheHubGot(id: string): Promise<unknown> {
    const path = `/internal/hubs/${id}`;
    await expect.poll(() => hub.calls.some((call) => call.method === 'PUT' && call.path === path)).toBe(true);
    return hub.calls.findLast((call) => call.method === 'PUT' && call.path === path)?.body.language;
  }

  for (const { lang, locale, business } of [
    { lang: 'es', locale: 'es-ES', business: 'Panadería Idioma E2E' },
    { lang: 'en', locale: 'en-GB', business: 'Bakery Language E2E' },
  ] as const) {
    test.describe(`with the page in ${lang}`, () => {
      test.use({ locale });

      test(`the code leads to «Create your business», the business and its notice in ${lang}, with no stop at Preferences`, async ({
        page,
      }) => {
        const errors = watchPageErrors(page);
        const email = await signUp(page, lang, lang);

        await review(page, lang, 'launcher', async () => {
          await expect(page.getByRole('heading', { name: t(lang, 'hubs.launch.first.title') })).toBeVisible();
        });
        expect(await languagesOf(page.request)).toEqual([lang]);

        const since = Date.now();
        const id = await createBusiness(page, lang, business);
        await review(page, lang, 'preparing', async () => {
          await expect(page.getByRole('heading', { name: business, exact: false })).toBeVisible();
        });
        expect(await languagesOf(page.request)).toEqual([lang, lang]);
        expect(await languageTheHubGot(id)).toBe(lang);
        expect(errors).toEqual([]);

        // Off the launcher first: it goes into a business that is ready by itself, and nobody answers there.
        await page.goto('about:blank');
        await reportBusinessReady(page.request, id);
        await waitForMail(email, since, asPattern(readyLine(lang, business)));
      });
    });
  }

  test.describe('after the sign-up', () => {
    test.use({ locale: 'es-ES' });

    test('Preferences still decides: English from there on, the business and its notice too', async ({ page }) => {
      const errors = watchPageErrors(page);
      const email = await signUp(page, 'es', 'preferences');
      expect(await languagesOf(page.request)).toEqual(['es']);

      await page.goto('/dashboard/account/preferences');
      await page.getByTestId('preferences-language').click();
      await page.locator('ion-popover ion-radio', { hasText: 'English' }).click();
      await expect(page.getByTestId('preferences-appearance')).toContainText(t('en', 'accounts.account.preferences.appearance'));
      await expect.poll(() => languagesOf(page.request)).toEqual(['en']);

      // The browser is still in Spanish: the server itself answers in the account's language (the SPA alone would
      // follow the session on the client), not only what the page paints afterwards.
      const launcher = await page.goto('/launch');
      expect(launcher?.headers()['content-language']).toBe('en');
      await expect(page.locator('html')).toHaveAttribute('lang', /^en\b/);
      const business = 'Bakery Preferences E2E';
      const since = Date.now();
      const id = await createBusiness(page, 'en', business);
      expect(await textsOfTheOtherLanguage(page, 'en')).toEqual([]);
      expect(await languagesOf(page.request)).toEqual(['en', 'en']);
      expect(await languageTheHubGot(id)).toBe('en');
      expect(errors).toEqual([]);

      await page.goto('about:blank');
      await reportBusinessReady(page.request, id);
      await waitForMail(email, since, asPattern(readyLine('en', business)));
    });
  });
});

test.describe('against the real Hub', () => {
  test.skip(!process.env.E2E_REAL_HUB, 'needs a real Hub on the stack’s Hub port (README «El Hub real de la e2e»)');
  test.use({ locale: 'es-ES' });

  test('the business opens in Spanish, with no stop at Preferences', async ({ page }) => {
    const email = await signUp(page, 'es', 'real');
    // The Hub keeps the address of every earlier pass (the rows removed here are the SaaS's): a new one each time.
    const stamp = Date.now();
    const business = `Horno Idioma ${stamp} E2E`;
    await page.getByTestId('create-name').locator('input').fill(business);
    const since = Date.now();
    await page.getByTestId('create-submit').click();

    await page.waitForURL(new RegExp(`^http://horno-idioma-${stamp}-e2e\\.localhost:${HUB_DOUBLE_PORT}/(?!auth)`), { timeout: 60_000 });
    await expect(page.locator('html')).toHaveAttribute('lang', /^es\b/);
    await expect(page.getByTestId('nav-home').first()).toContainText(t('es', 'home.title'));
    expect(await languagesOf(page.request)).toEqual(['es', 'es']);
    await waitForMail(email, since, asPattern(readyLine('es', business)));
    await page.screenshot({ path: shot('SIGNUP-LANGUAGE-real-hub-es'), fullPage: true });
  });
});
