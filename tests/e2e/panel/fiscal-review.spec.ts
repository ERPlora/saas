// The review of a signed authorisation (MIGRATION-TASK APP-FISCAL_GATEWAY; fiscal_gateway/WORKBOOK.md), at the three
// sizes of the migration (390×844, 834×1112, 1440×900), against the panel's own Django and the rows of
// fiscal_seed.py, whose upload runs the operation the Hub's upload runs. Mails are read from the panel's mail folder.
// flow: FISCAL-F05 — the review desk hears of the authorisation that waits, with the link to its review page and
// no document, and the owner hears of the decision in their language.
// flow: FISCAL-F03 — the documents are only decrypted on the review page, for the staff who decide.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { djangoPrint, expect, settled, shot, sidewaysScroll, signIn, test, waitForMail, watchPageErrors } from './fixtures';
import { PANEL_MAIL_DIR } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const PASSWORD = process.env.QA_PANEL_PASSWORD ?? 'e2e-panel';
const REVIEWER = { email: 'e2e-fiscal-reviewer@example.com', password: PASSWORD };
const OWNER = 'e2e-fiscal-owner@example.com';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const REVIEW_PATH = /\/admin\/fiscal\/representationgrant\/[0-9a-f-]{36}\/review\//;

/**
 * `fiscal_seed.py seed|clear`; `seed` files the authorisation and prints its id. Its mails land where the panel's
 * do (the panel's mail folder), as the upload's would on the server.
 */
function seed(action: 'seed' | 'clear'): string {
  return execFileSync('uv', ['run', 'python', 'tests/e2e/panel/fiscal_seed.py', action], {
    cwd: SAAS_DIR,
    env: { ...djangoEnv(true), EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend', EMAIL_FILE_PATH: PANEL_MAIL_DIR },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
    .trim()
    .split('\n')
    .at(-1) as string;
}

test.afterAll(() => {
  seed('clear');
});

/** `ready` at each size: no sideways scroll, a capture `APP-FISCAL_GATEWAY-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    expect(await sidewaysScroll(page), `${key} at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-FISCAL_GATEWAY-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test('FISCAL-F05: the review desk gets the link to review an authorisation and the owner hears of the decision', async ({ page }) => {
  const errors = watchPageErrors(page);
  const desk = djangoPrint('from django.conf import settings;print(settings.FISCAL_REVIEW_EMAIL)');
  const submitted = Date.now();
  const grant = seed('seed');

  // The desk's mail: the business, the link to the review page, and no document, tax ID nor name of a person.
  const link = await waitForMail(desk, submitted, REVIEW_PATH);
  expect(link).toContain(grant);
  const deskMail = await waitForMail(desk, submitted, /[\s\S]*/);
  expect(deskMail).toContain('Bar Fiscal');
  for (const personal of ['12345678Z', 'Olga Fiscal']) expect(deskMail).not.toContain(personal);
  // The owner's receipt, in Spanish.
  await waitForMail(OWNER, submitted, /Una persona de ERPlora la revisa/);

  await signIn(page.request, REVIEWER);
  await page.goto(link);
  const approve = page.getByRole('button', { name: 'Approve', exact: true });
  await atEverySize(page, 'FISCAL-F05', async () => {
    await expect(page.getByRole('heading', { name: 'Review the signed authorisation' })).toBeVisible();
    await expect(approve).toBeVisible();
  });

  const decided = Date.now();
  await approve.click();
  await expect(page.locator('.messagelist')).toContainText('Approved: ERPlora may now file the business');
  await expect(page.getByRole('button', { name: 'Withdraw the approval' })).toBeVisible();
  await waitForMail(OWNER, decided, /ERPlora ya puede enviar a Hacienda las facturas de Bar Fiscal con su sello/);
  expect(errors).toEqual([]);
});

test('FISCAL-F03: the documents of an authorisation are decrypted on its review page only', async ({ page }) => {
  const errors = watchPageErrors(page);
  const grant = seed('seed');
  await signIn(page.request, REVIEWER);

  await page.goto(`/admin/fiscal/representationgrant/${grant}/review/`);
  const documents = page.getByRole('link', { name: 'Open in a new tab' });
  await atEverySize(page, 'FISCAL-F03', async () => {
    await expect(page.getByRole('heading', { name: 'Documents' })).toBeVisible();
    await expect(documents).toHaveCount(2);
  });
  for (const link of await documents.all()) {
    const served = await page.request.get((await link.getAttribute('href')) as string);
    expect(served.status()).toBe(200);
    expect(served.headers()['content-type']).toBe('application/pdf');
    expect((await served.body()).subarray(0, 4).toString()).toBe('%PDF');
  }
  // The queue lists the authorisation without any document.
  await page.goto('/admin/fiscal/representationgrant/');
  await expect(page.getByRole('link', { name: 'Open in a new tab' })).toHaveCount(0);
  expect(errors).toEqual([]);
});
