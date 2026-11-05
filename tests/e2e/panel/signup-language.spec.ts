// flow: ACCOUNTS-F01
// Whoever signs up keeps the language of the page (ACCOUNTS-F01, ACCOUNTS-F22, HUBS-F01): the real sign-up on the
// launcher, the mailed code, «Create your business» in that language with no stop at Preferences, the business born
// in it (the row and what the Hub is told) and its «is ready» mail. Preferences still decides afterwards.
//
// The language comes from the browser (`locale` sends it as `Accept-Language`, as a real one does), never from a seed.
// Two parts, as panel/hubs-flows.spec.ts: the spec plays the Hub (`startHubDouble`) and reports the business ready, and
// «the real Hub» (`E2E_REAL_HUB=1`, README «El Hub real de la e2e»), where the business itself opens in the language.
// Accounts of this spec: `e2e-signup-lang-…@example.com`, removed before and after, with their businesses.
import { createHmac } from 'node:crypto';

import { type Page } from '@playwright/test';

import {
  businessIdOf,
  djangoPrint,
  expect,
  type HubDouble,
  internalSecret,
  shot,
  startHubDouble,
  submitSignInForm,
  test,
  waitForMail,
  waitForMailCode,
  watchPageErrors,
} from './fixtures';
import { type Lang, reviewOf, t, textsOfTheOtherLanguage } from './language-review';
import { HUB_DOUBLE_PORT } from './project';

const PREFIX = 'e2e-signup-lang-';
const PASSWORD = 'Signup-e2e-2026!';
const review = reviewOf('SIGNUP-LANGUAGE');

function removeOwnRows(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.models import Hub',
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `get_user_model().objects.filter(email__startswith="${PREFIX}").delete()`,
    ].join('\n'),
  );
}

/** What the SaaS keeps: the account's language, then that of each of its businesses. */
function languagesOf(email: string): string[] {
  return djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.models import HubMember',
      `user = get_user_model().objects.get(email="${email}")`,
      'print(user.language, *HubMember.objects.filter(user=user).values_list("hub__language", flat=True))',
    ].join('\n'),
  ).split(' ');
}

/** The first line of the «is ready» mail of `business` in `lang`, from Django's own catalogue. */
function readyLine(lang: Lang, business: string): string {
  return djangoPrint(
    [
      'from django.utils import translation',
      'from django.utils.translation import gettext',
      `translation.activate("${lang}")`,
      `print(gettext("%(business)s is ready: open it and start selling.") % {"business": "${business}"})`,
    ].join('\n'),
  );
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

/** The Hub's callback (`POST /internal/hubs/{id}/ready`), signed with the shared secret: the owner gets the mail. */
async function reportReady(page: Page, id: string): Promise<void> {
  const body = JSON.stringify({ id });
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac('sha256', internalSecret()).update(`${timestamp}.${body}`).digest('hex');
  const ready = await page.request.post(`/internal/hubs/${id}/ready`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': String(timestamp), 'X-Erplora-Signature': signature },
  });
  expect(ready.status(), await ready.text()).toBe(200);
}

test.beforeAll(removeOwnRows);
test.afterAll(removeOwnRows);

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
        expect(languagesOf(email)).toEqual([lang]);

        const since = Date.now();
        const id = await createBusiness(page, lang, business);
        await review(page, lang, 'preparing', async () => {
          await expect(page.getByRole('heading', { name: business, exact: false })).toBeVisible();
        });
        expect(languagesOf(email)).toEqual([lang, lang]);
        expect(await languageTheHubGot(id)).toBe(lang);
        expect(errors).toEqual([]);

        // Off the launcher first: it goes into a business that is ready by itself, and nobody answers there.
        await page.goto('about:blank');
        await reportReady(page, id);
        await waitForMail(email, since, asPattern(readyLine(lang, business)));
      });
    });
  }

  test.describe('after the sign-up', () => {
    test.use({ locale: 'es-ES' });

    test('Preferences still decides: English from there on, the business and its notice too', async ({ page }) => {
      const errors = watchPageErrors(page);
      const email = await signUp(page, 'es', 'preferences');
      expect(languagesOf(email)).toEqual(['es']);

      await page.goto('/dashboard/account/preferences');
      await page.getByTestId('preferences-language').click();
      await page.locator('ion-popover ion-radio', { hasText: 'English' }).click();
      await expect(page.getByTestId('preferences-appearance')).toContainText(t('en', 'accounts.account.preferences.appearance'));
      await expect.poll(() => languagesOf(email)).toEqual(['en']);

      // The browser is still in Spanish: the server itself answers in the account's language (the SPA alone would
      // follow the session on the client), not only what the page paints afterwards.
      const launcher = await page.goto('/launch');
      expect(launcher?.headers()['content-language']).toBe('en');
      await expect(page.locator('html')).toHaveAttribute('lang', /^en\b/);
      const business = 'Bakery Preferences E2E';
      const since = Date.now();
      const id = await createBusiness(page, 'en', business);
      expect(await textsOfTheOtherLanguage(page, 'en')).toEqual([]);
      expect(languagesOf(email)).toEqual(['en', 'en']);
      expect(await languageTheHubGot(id)).toBe('en');
      expect(errors).toEqual([]);

      await page.goto('about:blank');
      await reportReady(page, id);
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
    expect(languagesOf(email)).toEqual(['es', 'es']);
    await waitForMail(email, since, asPattern(readyLine('es', business)));
    await page.screenshot({ path: shot('SIGNUP-LANGUAGE-real-hub-es'), fullPage: true });
  });
});
