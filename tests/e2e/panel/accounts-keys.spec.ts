// The API keys of the SaaS from the admin (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-4), at the three sizes of
// the migration (390×844, 834×1112, 1440×900): a superuser issues a key for a team account and sees it once (G101), the
// key opens what its permission opens and nothing else (G102), and revoking it cuts it at once (G103). In
// accounts/WORKBOOK.md: G101 = F31, G102 = F32, G103 = F33. The person's own keys (Account › API keys: create with
// «Confirm it's you», use, revoke) are account.spec.ts's. Accounts of this spec: `e2e-acc4k-…@example.com`.
import { type Page } from '@playwright/test';

import {
  djangoPrint,
  expect,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  signInThroughPage,
  test,
  watchPageErrors,
} from './fixtures';

const PREFIX = 'e2e-acc4k-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

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

/** An account with its address proven; `role` makes it a superuser or a team account of support. */
function createAccount(email: string, role: 'superuser' | 'support' | 'customer'): { email: string; password: string } {
  const create =
    role === 'customer'
      ? `get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", language="en")`
      : `services.create_platform_user("${email}", ${role === 'superuser' ? 'services.PLATFORM_ADMIN' : 'services.PLATFORM_SUPPORT'}, "${PASSWORD}")[0]`;
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      'from accounts import services',
      `user = ${create}`,
      'user.language = "en"; user.save(update_fields=["language"])',
      'EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})',
    ].join('\n'),
  );
  return { email, password: PASSWORD };
}

/** Each size: the page as `ready` leaves it, no sideways scroll, and its shot (`fullPage` off for a page as long as the
 *  API's reference, whose full shot is tens of thousands of pixels tall). */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>, fullPage = true): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ACCOUNTS-4-${key}-${size.name}`), fullPage });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.beforeAll(() => removeAccounts());
test.afterAll(() => removeAccounts());

test('ACCOUNTS-G101 · G102 · G103 · a superuser issues a key for a team account: shown once, opens its permission, cut by revoking', async ({
  page,
  playwright,
}) => {
  const errors = watchPageErrors(page);
  const root = createAccount(address('root'), 'superuser');
  const teammate = createAccount(address('qa'), 'support');
  createAccount(address('customer'), 'customer');
  await signIn(page.request, root);

  await page.goto('/admin/accounts/apikey/add/');
  const form = page.locator('#apikey_form');
  await atEverySize(page, 'ACCOUNTS-G101-form', async () => {
    await expect(form).toBeVisible();
  });
  // Team accounts only: the customer is not offered.
  const offered = await form.locator('select[name="user"] option').allTextContents();
  expect(offered.some((text) => text.includes(teammate.email))).toBe(true);
  expect(offered.some((text) => text.includes(`${PREFIX}customer`))).toBe(false);
  await form.locator('select[name="user"]').selectOption({ label: teammate.email });
  await form.locator('input[name="name"]').fill('QA monitor');
  await form.locator('input[name="scopes"][value="hubs.read"]').check();
  await form.locator('select[name="expires_in_days"]').selectOption('30');
  await form.locator('input[name="_save"]').click();

  const shown = page.locator('[data-api-key-secret]');
  await expect(shown).toBeVisible();
  const secret = (await shown.getAttribute('data-api-key-secret')) ?? '';
  expect(secret).toMatch(/^erps_live_[A-Za-z0-9]{48}$/);
  await atEverySize(page, 'ACCOUNTS-G101-issued', async () => {
    await expect(page.getByText('Copy it now: it will not be shown again.')).toBeVisible();
  });
  // Never again: not on the list, not on the key's page.
  await page.getByRole('link', { name: 'Back to the API keys' }).click();
  await expect(page.locator('#result_list')).toContainText('QA monitor');
  expect(await page.content()).not.toContain(secret);

  // The key is a program's, without the browser's session: what hubs.read opens (the businesses of its account: a team
  // account is no member of any), and nothing else.
  const program = await playwright.request.newContext({ baseURL: new URL(page.url()).origin });
  const read = await program.get('/api/hubs/businesses?limit=10&offset=0', { headers: { Authorization: `Bearer ${secret}` } });
  expect(read.status()).toBe(200);
  expect(((await read.json()) as { rows: unknown[] }).rows).toEqual([]);
  const account = await program.get('/api/accounts/api-keys', { headers: { 'X-Api-Key': secret } });
  expect([account.status(), ((await account.json()) as { error: { code: string } }).error.code]).toEqual([
    403,
    'api_key_not_allowed',
  ]);

  // Revoked from the admin: the next call is refused.
  await page.locator('#result_list tbody tr', { hasText: 'QA monitor' }).locator('input.action-select').check();
  await page.locator('select[name="action"]').selectOption('revoke');
  await page.locator('button[name="index"]').click();
  await expect(page.locator('.messagelist')).toContainText('Keys revoked: 1.');
  const after = await program.get('/api/hubs/businesses?limit=10&offset=0', { headers: { Authorization: `Bearer ${secret}` } });
  expect([after.status(), ((await after.json()) as { error: { code: string } }).error.code]).toEqual([401, 'api_key_invalid']);
  await program.dispose();
  expect(errors).toEqual([]);
});

test('ACCOUNTS-G105 · G13 · the API documentation: for signed-in accounts, from Account › API keys, nothing from outside', async ({
  page,
  context,
}) => {
  const errors = watchPageErrors(page);
  // Nothing from outside is loaded, nor even tried: ReDoc's own logo (cdn.redoc.ly) is not in the copy served here, so
  // the documentation's console has no refusal of the policy either.
  const outside: string[] = [];
  context.on('requestfinished', (request) => {
    const url = new URL(request.url());
    if (url.protocol !== 'blob:' && !['localhost', '127.0.0.1'].includes(url.hostname)) outside.push(request.url());
  });
  const ana = createAccount(address('docs'), 'customer');

  // Signed out: the sign-in, then back to the documentation.
  await page.goto('/api/docs');
  await expect(page).toHaveURL(/\/launch\?next=/);
  expect(new URL(page.url()).searchParams.get('next')).toBe('/api/docs');
  await signInThroughPage(page, ana);
  await expect(page).toHaveURL(/\/api\/docs$/);
  await expect(page.locator('#redoc-ui')).toContainText('/api/accounts/api-keys');

  // From Account › API keys: the link opens it beside the panel.
  await page.goto('/account/api-keys');
  const [docs] = await Promise.all([context.waitForEvent('page'), page.getByTestId('api-keys-docs').click()]);
  const docsErrors = watchPageErrors(docs);
  const consoleErrors: string[] = [];
  docs.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  await expect(docs).toHaveURL(/\/api\/docs$/);
  // Again with the console watched from its first line.
  await docs.reload();
  await atEverySize(docs, 'ACCOUNTS-G105', async () => {
    await expect(docs.getByRole('heading', { name: /ERPlora Cloud API/ }).first()).toBeVisible();
    await expect(docs.locator('#redoc-ui')).toContainText('/api/accounts/api-keys');
  }, false);
  expect(outside).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect([...errors, ...docsErrors]).toEqual([]);
});
