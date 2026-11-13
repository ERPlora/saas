// The platform of erplora.com (accounts/WORKBOOK.md), at the three sizes
// (390×844, 834×1112, 1440×900):
//   - ACCOUNTS-F47 (moving around the panel): the menu has «Businesses», «Store», «Billing» and «Account», in the
//     side menu from 1440 px and in its drawer below; each entry opens its page and is marked as the current one;
//     in Spanish, «Negocios», «Tienda», «Facturación» and «Cuenta».
//   - ACCOUNTS-F43 (maintenance): the staff turns on «Maintenance mode» in the admin's «Site settings» with
//     its message; a visitor gets the maintenance page (503) in English and in Spanish; the staff keeps using the panel
//     and signs in again through the launcher on its way to the admin; turned off, everyone enters.
// Accounts of this spec: `e2e-acc5-…`.
import { type Browser, type Page } from '@playwright/test';

import {
  captureAtEverySize,
  closeMenu,
  createAccountWarm,
  djangoPrintWarm,
  expect,
  openMenu,
  removeAccountsWarm,
  signIn,
  signInThroughPage,
  test,
  watchPageErrors,
} from './fixtures';

const atEverySize = captureAtEverySize('APP-ACCOUNTS-5');

const PREFIX = 'e2e-acc5-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const SITE_SETTINGS = '/admin/base/sitesettings/';

const removeAccounts = () => removeAccountsWarm(PREFIX);

/** An account with its address proven; `staff` makes it a superuser of the admin. */
const createAccount = (name: string, { staff = false, language = 'en' as 'en' | 'es' } = {}) =>
  createAccountWarm(`${PREFIX}${name}-${Date.now()}@example.com`, PASSWORD, { role: staff ? 'superuser' : 'customer', language });

/** The switch as the database has it, for a run that died half-way: off. */
async function maintenanceOffInTheDatabase(): Promise<void> {
  await djangoPrintWarm('from base.models import SiteSettings\nSiteSettings.objects.update(maintenance_mode=False, maintenance_message_en="", maintenance_message_es="")');
}

/** A visitor of its own, without a session, in `locale`. */
async function visitor(browser: Browser, baseURL: string, locale: string): Promise<Page> {
  const context = await browser.newContext({ baseURL, locale, extraHTTPHeaders: { 'Accept-Language': locale } });
  return context.newPage();
}

/** The staff's «Site settings»: the switch and the English message, saved; what the admin then says. */
async function setMaintenance(page: Page, on: boolean, message = ''): Promise<string> {
  await page.goto(SITE_SETTINGS);
  await expect(page).toHaveURL(/\/admin\/base\/sitesettings\/[0-9a-f-]+\/change\/$/);
  const box = page.locator('#id_maintenance_mode');
  if ((await box.isChecked()) !== on) await box.click();
  await page.locator('#id_maintenance_message_en').fill(message);
  await page.locator('input[name="_save"]').click();
  return (await page.locator('.messagelist').innerText()).trim();
}

test.beforeAll(() => removeAccounts());
test.afterAll(async () => {
  await maintenanceOffInTheDatabase();
  await removeAccounts();
});

test('ACCOUNTS-F47 · the menu opens Businesses, Store, Billing and Account at every size, in English and in Spanish', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, await createAccount('nav'));

  await page.goto('/dashboard/businesses');
  await atEverySize(
    page,
    'ACCOUNTS-G106',
    async () => {
      await openMenu(page);
      await expect(page.locator('ion-menu .nav-item')).toHaveText(['Businesses', 'Store', 'Billing', 'Account']);
      await expect(page.locator('ion-menu .nav-item[aria-current="page"]')).toHaveText('Businesses');
    },
    { after: () => closeMenu(page) },
  );

  for (const [label, path] of [
    ['Billing', /\/dashboard\/billing/],
    ['Store', /\/dashboard\/store/],
    ['Account', /\/dashboard\/account/],
    ['Businesses', /\/dashboard\/businesses/],
  ] as const) {
    await openMenu(page);
    await page.locator('ion-menu .nav-item').filter({ hasText: label }).click();
    await expect(page).toHaveURL(path);
    await expect(page.locator('ion-menu .nav-item[aria-current="page"]')).toHaveText(label);
  }
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F47 · the menu speaks Spanish', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, await createAccount('nav-es', { language: 'es' }));

  await page.goto('/dashboard/businesses');
  await atEverySize(
    page,
    'ACCOUNTS-G106-es',
    async () => {
      await openMenu(page);
      await expect(page.locator('ion-menu .nav-item')).toHaveText(['Negocios', 'Tienda', 'Facturación', 'Cuenta']);
    },
    { after: () => closeMenu(page) },
  );
  expect(errors).toEqual([]);
});

test('ACCOUNTS-F43 · the staff turns maintenance on in the admin: visitors get the 503 page, the staff keeps working and signs in again', async ({
  page,
  browser,
  baseURL,
}) => {
  test.setTimeout(180_000);
  const staff = await createAccount('staff', { staff: true });
  await signIn(page.request, staff);

  try {
    // Django's own «… was changed successfully.» comes first; the switch's consequence follows it.
    expect(await setMaintenance(page, true)).toContain('Maintenance mode is on: only the ERPlora staff with a session uses erplora.com.');

    // A visitor in English and one in Spanish: the page, 503, with its «Retry».
    const english = await visitor(browser, baseURL!, 'en-US');
    const answer = await english.goto('/launch');
    expect(answer?.status()).toBe(503);
    expect(answer?.headers()['retry-after']).toBe('300');
    await atEverySize(english, 'ACCOUNTS-G82-en', async () => {
      await expect(english.locator('h1')).toHaveText('We will be back soon');
      await expect(english.locator('.error-page__code')).toHaveText('503 · Maintenance');
      await expect(english.getByRole('link', { name: 'Retry' })).toBeVisible();
      await expect(english.getByRole('link', { name: 'Contact Support' })).toBeVisible();
    });
    const spanish = await visitor(browser, baseURL!, 'es-ES');
    expect((await spanish.goto('/'))?.status()).toBe(503);
    await atEverySize(spanish, 'ACCOUNTS-G82-es', async () => {
      await expect(spanish.locator('h1')).toHaveText('Volvemos enseguida');
      await expect(spanish.locator('main')).toContainText('Estamos mejorando ERPlora. Vuelve en unos minutos; tus datos están a salvo.');
      await expect(spanish.getByRole('link', { name: 'Reintentar' })).toBeVisible();
      await expect(spanish.getByRole('link', { name: 'Contactar Soporte' })).toBeVisible();
    });

    // The staff's own message replaces the page's text.
    await setMaintenance(page, true, 'Back at 14:00 CET.');
    await english.reload();
    await expect(english.locator('main')).toContainText('Back at 14:00 CET.');

    // The staff keeps using the panel.
    const errors = watchPageErrors(page);
    expect((await page.goto('/dashboard/businesses'))?.status()).toBe(200);
    await expect(page.locator('ion-menu .nav-item').first()).toBeAttached();
    expect(errors).toEqual([]);

    // A staff member without a session still signs in, on the way to the admin.
    const again = await visitor(browser, baseURL!, 'en-US');
    await again.goto('/admin/');
    await expect(again).toHaveURL(/\/launch\?next=%2Fadmin%2F|\/launch\?next=\/admin\//);
    await signInThroughPage(again, staff);
    await expect(again).toHaveURL(/\/admin\/$/);
    await expect(again.locator('#site-name')).toHaveText('ERPlora Cloud');
    await again.context().close();

    // Turned off, everyone enters.
    expect(await setMaintenance(page, false)).toContain('Maintenance mode is off: erplora.com is open to everyone.');
    expect((await english.goto('/launch'))?.status()).toBe(200);
    await english.context().close();
    await spanish.context().close();
  } finally {
    if (page.url().startsWith(baseURL!)) await setMaintenance(page, false).catch(() => undefined);
    await maintenanceOffInTheDatabase();
  }
});
