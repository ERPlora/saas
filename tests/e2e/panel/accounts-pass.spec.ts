// The way back from a business to erplora.com with a one-time pass (accounts/WORKBOOK.md ACCOUNTS-F29, the Hub's BASE-F11;
// saas#190), on its screens at the three sizes (390×844, 834×1112, 1440×900): a pass the business signed opens erplora.com
// already signed in, on the plan of that business or on the business (a browser without the session of erplora.com, as
// the installed app's); the same pass a second time, one not signed as the business signs it and one of an account that
// is no member open nothing, and the error page says why, in English and in Spanish. The Hub is played: the spec signs
// the pass as the Hub does (`django.core.signing.dumps` keyed with the shared secret, salt `erplora.hub-pass.v1`).
// Accounts of this spec: `e2e-pass-…@example.com`, removed before and after.
import { type Browser, type Page } from '@playwright/test';

import { captureAtEverySize, djangoPrint, expect, signInThroughPage, test, watchPageErrors } from './fixtures';

const PREFIX = 'e2e-pass-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const atEverySize = captureAtEverySize('ACCOUNTS-F29');

/** A fresh address of this spec, never used before. */
const address = (name: string) => `${PREFIX}${name}-${Date.now()}@example.com`;

function removeAccounts(): void {
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.models import Hub',
      `Hub.objects.filter(members__user__email__startswith="${PREFIX}").delete()`,
      `get_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
    ].join('\n'),
  );
}

/** An account with its address proven, as one that signed in before. */
function createAccount(email: string): { email: string; password: string } {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", first_name="Ana", last_name="García")`,
      'EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)',
    ].join('\n'),
  );
  return { email, password: PASSWORD };
}

/** A business of `email` made by its operation (its owner is `email`): its slug and its id. */
function businessOf(email: string, name: string): { slug: string; id: string } {
  const [slug, id] = djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.tests.conftest import create_business',
      `hub = create_business(get_user_model().objects.get(email="${email}"), name="${name}")`,
      'print(hub.slug, hub.id)',
    ].join('\n'),
  ).split(' ');
  return { slug, id };
}

/** The pass of `email` for `slug`, signed as the Hub signs it; `key` replaces the shared secret (a forged pass). */
function pass(email: string, slug: string, next: 'plan' | 'business', key?: string): string {
  return djangoPrint(
    [
      'import uuid',
      'from django.conf import settings',
      'from django.contrib.auth import get_user_model',
      'from django.core import signing',
      `user = get_user_model().objects.get(email="${email}")`,
      `payload = {"user": str(user.pk), "hub": "${slug}", "next": "${next}", "nonce": uuid.uuid4().hex}`,
      `print(signing.dumps(payload, key=${key ? JSON.stringify(key) : 'settings.INTERNAL_SHARED_SECRET'}, salt="erplora.hub-pass.v1"))`,
    ].join('\n'),
  );
}

const follow = (token: string) => `/hub-pass/?pass=${encodeURIComponent(token)}`;
const planOf = (id: string) => `/dashboard/store/plans?business=${id}`;

/** A browser of its own without the session of erplora.com (the device's, opened by the installed app), in `locale`. */
async function freshBrowser(browser: Browser, baseURL: string, locale = 'en-US'): Promise<Page> {
  const context = await browser.newContext({ baseURL, locale, extraHTTPHeaders: { 'Accept-Language': locale } });
  return context.newPage();
}

test.beforeAll(() => removeAccounts());
test.afterAll(() => removeAccounts());

test('ACCOUNTS-F29 · a pass of the business opens erplora.com signed in, on the plan or on the business', async ({
  browser,
  baseURL,
}) => {
  const ana = createAccount(address('owner'));
  const bakery = businessOf(ana.email, 'Panadería Ana');

  const page = await freshBrowser(browser, baseURL!);
  const errors = watchPageErrors(page);
  await page.goto(follow(pass(ana.email, bakery.slug, 'plan')));
  await atEverySize(page, 'plan', async () => {
    await expect(page).toHaveURL(planOf(bakery.id));
    await expect(page.getByTestId('store-plans')).toBeVisible();
  });
  expect(errors).toEqual([]);

  const other = await freshBrowser(browser, baseURL!);
  const otherErrors = watchPageErrors(other);
  await other.goto(follow(pass(ana.email, bakery.slug, 'business')));
  await atEverySize(other, 'business', async () => {
    await expect(other).toHaveURL(new RegExp(`/dashboard/businesses/${bakery.id}(/[a-z-]+)?$`));
    await expect(other.getByTestId('business-header')).toContainText('Panadería Ana');
  });
  expect(otherErrors).toEqual([]);
});

test('ACCOUNTS-F29 · a pass followed twice opens nothing the second time: signing in goes on to the plan', async ({
  browser,
  baseURL,
}) => {
  const ana = createAccount(address('twice'));
  const bakery = businessOf(ana.email, 'Panadería Dos');
  const token = pass(ana.email, bakery.slug, 'plan');
  const first = await freshBrowser(browser, baseURL!);
  await first.goto(follow(token));
  await expect(first).toHaveURL(planOf(bakery.id));

  const page = await freshBrowser(browser, baseURL!);
  const errors = watchPageErrors(page);
  await page.goto(follow(token));
  await atEverySize(page, 'expired', async () => {
    await expect(page).toHaveURL(/\/login\/error\?code=pass_expired&next=/);
    await expect(page.getByTestId('login-error-badge')).toHaveText('410 · Link expired');
    await expect(page.getByRole('heading', { name: 'This link from your business has expired' })).toBeVisible();
  });
  await page.getByTestId('login-error-action').click();
  await expect(page).toHaveURL(`/launch?next=${encodeURIComponent(planOf(bakery.id))}`);
  await signInThroughPage(page, ana);
  await expect(page).toHaveURL(planOf(bakery.id));
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F29 · a pass not signed as the business signs it opens nothing, in English and in Spanish', async ({
  browser,
  baseURL,
}) => {
  const ana = createAccount(address('forged'));
  const bakery = businessOf(ana.email, 'Panadería Falsa');
  const forged = pass(ana.email, bakery.slug, 'plan', 'not-the-shared-secret');

  const page = await freshBrowser(browser, baseURL!);
  const errors = watchPageErrors(page);
  await page.goto(follow(forged));
  await atEverySize(page, 'invalid', async () => {
    await expect(page).toHaveURL('/login/error?code=invalid_pass');
    await expect(page.getByTestId('login-error-badge')).toHaveText('400 · Invalid link');
    await expect(page.getByRole('heading', { name: 'This link from your business is not valid' })).toBeVisible();
  });
  expect(errors).toEqual([]);

  const spanish = await freshBrowser(browser, baseURL!, 'es-ES');
  const spanishErrors = watchPageErrors(spanish);
  await spanish.goto(follow(forged));
  await atEverySize(spanish, 'invalid-es', async () => {
    await expect(spanish.getByTestId('login-error-badge')).toHaveText('400 · Enlace no válido');
    await expect(spanish.getByRole('heading', { name: 'Este enlace de tu negocio no es válido' })).toBeVisible();
    await expect(spanish.getByTestId('login-error-action')).toHaveText('Iniciar sesión');
  });
  // Nothing opened: erplora.com still asks to sign in.
  await spanish.goto('/dashboard/businesses');
  await expect(spanish).toHaveURL(/\/launch\?next=/);
  expect(spanishErrors).toEqual([]);
});

test('ACCOUNTS-F29 · a pass of an account that is no member of that business opens nothing', async ({ browser, baseURL }) => {
  const ana = createAccount(address('member'));
  const stranger = createAccount(address('stranger'));
  const bakery = businessOf(ana.email, 'Panadería Ajena');

  const page = await freshBrowser(browser, baseURL!);
  const errors = watchPageErrors(page);
  await page.goto(follow(pass(stranger.email, bakery.slug, 'plan')));
  await expect(page).toHaveURL(`/login/error?code=not_a_member&hub=${bakery.slug}`);
  await expect(page.getByRole('heading', { name: "You don't have access to this hub" })).toBeVisible();
  await page.goto('/dashboard/businesses');
  await expect(page).toHaveURL(/\/launch\?next=/);
  expect(errors).toEqual([]);
});
