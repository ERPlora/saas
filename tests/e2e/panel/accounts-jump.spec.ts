// The jumps between erplora.com and a business (accounts/WORKBOOK.md), on their screens at three sizes (390×844,
// 834×1112, 1440×900): into a business with a one-time code (F28, also with the sign-in on erplora.com on the way,
// then the business), what the business learns of the person (F12), back to erplora.com from a business (F29) and the
// account on its own, as the installed app opens it (F30). Each test names its flow of accounts/WORKBOOK.md in its
// title.
// The Hub is played at its own addresses (`http://<slug>.localhost:8000/…`, the panel's HUB_CALLBACK_TEMPLATE): the spec
// receives the form the browser posts to the business's callback and redeems the code as the Hub does, signed, at the
// real `/internal/auth/redeem`. The Hub's own half (its callback, its session) runs in every e2e of the Hub, whose sign-in
// goes through this SaaS (hub `tests/e2e/helpers.ts`). Accounts of this spec: `e2e-acc4-…@example.com`, removed before
// and after; their businesses are created by `hubs.business.create`, as the panel creates them.
import { createHmac } from 'node:crypto';

import { type APIRequestContext, type Page } from '@playwright/test';

import {
  captureAtEverySize,
  createAccountWarm,
  djangoPrintWarm,
  expect,
  internalSecret,
  removeAccountsWarm,
  sessionOf,
  signIn,
  signInThroughPage,
  test,
  watchPageErrors,
} from './fixtures';

const atEverySize = captureAtEverySize('APP-ACCOUNTS-4');

const PREFIX = 'e2e-acc4-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const STATE = 'state-of-the-browser-that-started-the-jump-0123456789';

/** A fresh address of this spec, never used before. */
const address = (name: string) => `${PREFIX}${name}-${Date.now()}@example.com`;

const removeAccounts = () => removeAccountsWarm(PREFIX);

/** An account with its address proven, as one that signed in before; the panel speaks its `language`. */
const createAccount = (email: string, language: 'en' | 'es' = 'en') =>
  createAccountWarm(email, PASSWORD, { firstName: 'Ana', lastName: 'García', language });

/** A business of `email` made by its operation (its owner is `email`); returns its slug. */
function businessOf(email: string, name: string): Promise<string> {
  return djangoPrintWarm(
    [
      'from django.contrib.auth import get_user_model',
      'from hubs.tests.conftest import create_business',
      `print(create_business(get_user_model().objects.get(email="${email}"), name="${name}").slug)`,
    ].join('\n'),
  );
}

/** What the browser posted to a business's callback: the form of the jump. */
interface Jump {
  url: string;
  fields: Record<string, string>;
}

/** Plays every business's host: records the jumps posted to `/auth/callback` and answers each with a page. */
async function playTheHubs(page: Page): Promise<Jump[]> {
  const jumps: Jump[] = [];
  await page.route(/^http:\/\/[\w-]+\.localhost:8000\//, async (route) => {
    const request = route.request();
    if (request.method() === 'POST') {
      jumps.push({ url: request.url(), fields: Object.fromEntries(new URLSearchParams(request.postData() ?? '')) });
    }
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Hub</h1>' });
  });
  return jumps;
}

/** `POST /internal/auth/redeem` signed as the Hub signs it (v1, the body), from `request`'s origin (the panel). */
async function redeem(request: APIRequestContext, body: Record<string, string>) {
  const raw = JSON.stringify(body);
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac('sha256', await internalSecret()).update(`${timestamp}.${raw}`).digest('hex');
  const response = await request.post('/internal/auth/redeem', {
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': String(timestamp), 'X-Erplora-Signature': signature },
    data: raw,
  });
  return { status: response.status(), body: (await response.json()) as Record<string, unknown> };
}

/** The item of the panel's side menu labelled `label` (`ion-item.nav-item` of the shell). */
const menuItem = (page: Page, label: string) =>
  page.locator('ion-item.nav-item').filter({ has: page.locator('ion-label', { hasText: new RegExp(`^${label}$`) }) });

/** Where the sign-in sends back to, once signed in: `next` of `/launch`. */
async function nextOfTheSignIn(page: Page): Promise<string | null> {
  await expect(page).toHaveURL(/\/launch\?/);
  return new URL(page.url()).searchParams.get('next');
}

test.beforeAll(() => removeAccounts());
// What redeem signs with, read here and not inside a test (fixtures.ts, internalSecret).
test.beforeAll(() => internalSecret());
test.afterAll(() => removeAccounts());

test('ACCOUNTS-F28 · ACCOUNTS-F12 · a member enters the business with a one-time code: posted, bound to it and spent once', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const ana = await createAccount(address('owner'), 'es');
  const slug = await businessOf(ana.email, 'Panadería Ana');
  const jumps = await playTheHubs(page);
  await signIn(page.request, ana);

  await page.goto(`/hub-login/?hub=${slug}&next=/sales&state=${STATE}`);

  await expect.poll(() => jumps.length).toBe(1);
  const [jump] = jumps;
  expect(jump.url).toBe(`http://${slug}.localhost:8000/auth/callback`);
  // Never in an address: the page posted it, and the business's page is the last one.
  await expect(page).toHaveURL(`http://${slug}.localhost:8000/auth/callback`);
  expect(Object.keys(jump.fields).sort()).toEqual(['code', 'next', 'state']);
  expect([jump.fields.next, jump.fields.state]).toEqual(['/sales', STATE]);

  const other = await redeem(page.request, { code: jump.fields.code, hub: 'otro-negocio' });
  expect([other.status, (other.body.error as { code: string }).code]).toEqual([400, 'invalid_code']);
  const entered = await redeem(page.request, { code: jump.fields.code, hub: slug });
  expect(entered.status).toBe(200);
  const userId = (await sessionOf(page.request)).user?.id;
  expect(entered.body).toEqual({ user_id: userId, email: ana.email, name: 'Ana García', locale: 'es', role: 'hub_owner' });
  const again = await redeem(page.request, { code: jump.fields.code, hub: slug });
  expect([again.status, (again.body.error as { code: string }).code]).toEqual([400, 'invalid_code']);
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F28 · signed out, the jump signs in on erplora.com and goes on to the business with its state', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const ana = await createAccount(address('signed-out'));
  const slug = await businessOf(ana.email, 'Peluquería Ana');
  const jumps = await playTheHubs(page);

  await page.goto(`/hub-login/?hub=${slug}&next=/appointments&state=${STATE}`);
  expect(await nextOfTheSignIn(page)).toBe(`/hub-login/?hub=${slug}&next=/appointments&state=${STATE}`);
  await expect(page.getByTestId('login-form')).toBeVisible();
  await signInThroughPage(page, ana);

  await expect.poll(() => jumps.length).toBe(1);
  expect([jumps[0].url, jumps[0].fields.next, jumps[0].fields.state]).toEqual([
    `http://${slug}.localhost:8000/auth/callback`,
    '/appointments',
    STATE,
  ]);
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F28 · a jump to a business of others is refused on its page, naming only its host', async ({ page }) => {
  const errors = watchPageErrors(page);
  const owner = await createAccount(address('other-owner'));
  const slug = await businessOf(owner.email, 'Bar de Otros');
  const stranger = await createAccount(address('stranger'));
  const jumps = await playTheHubs(page);
  await signIn(page.request, stranger);

  await page.goto(`/hub-login/?hub=${slug}&next=/&state=${STATE}`);

  await expect(page).toHaveURL(`/login/error?code=not_a_member&hub=${slug}`);
  await atEverySize(page, 'ACCOUNTS-G98-not-a-member', async () => {
    await expect(page.getByRole('heading', { name: "You don't have access to this hub" })).toBeVisible();
    await expect(page.getByTestId('login-error-badge')).toHaveText('403 · No access');
    await expect(page.locator('p.auth-lead')).toContainText(`${slug}.localhost:8000`);
    await expect(page.locator('p.auth-lead')).not.toContainText('Bar de Otros');
  });
  expect(jumps).toEqual([]);
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F28 · too many jumps in a few minutes wait, without a code', async ({ page }) => {
  const errors = watchPageErrors(page);
  const ana = await createAccount(address('brake'));
  const slug = await businessOf(ana.email, 'Frutería Ana');
  await signIn(page.request, ana);
  const jump = () => page.request.get(`/hub-login/?hub=${slug}&next=/&state=${STATE}`, { maxRedirects: 0 });

  for (let index = 0; index < 20; index += 1) expect((await jump()).status()).toBe(200);
  const refused = await jump();

  expect([refused.status(), refused.headers().location]).toEqual([302, '/login/error?code=too_many']);
  await page.goto('/login/error?code=too_many');
  await atEverySize(page, 'ACCOUNTS-G98-too-many', async () => {
    await expect(page.getByRole('heading', { name: 'Too many attempts' })).toBeVisible();
    await expect(page.getByTestId('login-error-badge')).toHaveText('429 · Too many attempts');
  });
  const minted = await djangoPrintWarm(
    `from accounts.models import AuthExchangeCode\nprint(AuthExchangeCode.objects.filter(user__email="${ana.email}").count())`,
  );
  expect(minted).toBe('20');
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F29 · from a business, an erplora.com page opens with the session of erplora.com, or after signing in', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const ana = await createAccount(address('back'));

  // Signed out (another browser, or the session ended): the sign-in, then the page the business linked to.
  await page.goto('/dashboard/account/security');
  expect(await nextOfTheSignIn(page)).toBe('/dashboard/account/security');
  await signInThroughPage(page, ana);
  await expect(page).toHaveURL('/dashboard/account/security');

  // Signed in on erplora.com (the browser came from it to the business): straight in, no password again.
  await page.goto('/dashboard/account/profile');
  await atEverySize(page, 'ACCOUNTS-G100', async () => {
    await expect(page).toHaveURL('/dashboard/account/profile');
    await expect(page.getByRole('heading', { name: 'Your details' })).toBeVisible();
  });
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F30 · the app opens the account on its own: its old address, the sign-in on the way, nothing that sells', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  const ana = await createAccount(address('app'));

  await page.goto('/dashboard/profile/?surface=account');
  expect(await nextOfTheSignIn(page)).toBe('/dashboard/account/profile?surface=account');
  await signInThroughPage(page, ana);
  await expect(page).toHaveURL('/dashboard/account/profile?surface=account');

  await atEverySize(page, 'ACCOUNTS-G113', async () => {
    await expect(page.getByRole('heading', { name: 'Your details' })).toBeVisible();
    // The Store sells: the account surface leaves it out of the menu.
    await expect(menuItem(page, 'Store')).toHaveCount(0);
    await expect(menuItem(page, 'Businesses')).toHaveCount(1);
  });
  // Without the mark (the browser's own panel) the Store is in the menu: the check above can fail.
  await page.goto('/dashboard/account/profile?surface=web');
  await expect(page.getByRole('heading', { name: 'Your details' })).toBeVisible();
  await expect(menuItem(page, 'Store')).toHaveCount(1);
  expect(errors).toEqual([]);
});
