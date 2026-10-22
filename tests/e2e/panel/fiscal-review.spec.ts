// The review of a signed authorisation (MIGRATION-TASK APP-FISCAL_GATEWAY; fiscal_gateway/WORKBOOK.md), at the three
// sizes of the migration (390×844, 834×1112, 1440×900), against the panel's own Django and the rows of
// fiscal_seed.py, whose upload runs the operation the Hub's upload runs. Mails are read from the panel's mail folder.
// flow: FISCAL-F05 — the review desk hears of the authorisation that waits, with the link to its review page and
// no document, and the owner hears of the decision in their language.
// flow: FISCAL-F03 — the documents are only decrypted on the review page, for the staff who decide.
// flow: FISCAL-F06 — ERPlora's stamp and signature as representative: the queue warns while there is none, the
// staff upload a PNG, see it, download the model a business receives with it, and remove it.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
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

/** A synthetic stamp (a ring and a text on a transparent background), as base64 PNG; never ERPlora's real one. */
function syntheticStamp(): Buffer {
  const encoded = djangoPrint(
    [
      'import base64, io',
      'from PIL import Image, ImageDraw',
      "image = Image.new('RGBA', (320, 120), (0, 0, 0, 0))",
      'draw = ImageDraw.Draw(image)',
      'draw.ellipse((10, 10, 110, 110), outline=(30, 60, 160, 255), width=6)',
      "draw.text((130, 52), 'E2E STAMP', fill=(30, 60, 160, 255))",
      'buffer = io.BytesIO()',
      "image.save(buffer, 'PNG')",
      'print(base64.b64encode(buffer.getvalue()).decode())',
    ].join('\n'),
  );
  return Buffer.from(encoded, 'base64');
}

/** Pages of the model and images on its first page, read by pypdf from the bytes the admin served. */
async function modelShape(page: Page, href: string, name: string): Promise<{ pages: number; images: number; text: string }> {
  const served = await page.request.get(href);
  expect(served.status()).toBe(200);
  expect(served.headers()['content-type']).toBe('application/pdf');
  const file = shot(name).replace(/\.png$/, '.pdf');
  writeFileSync(file, await served.body());
  const read = djangoPrint(
    [
      'import json',
      'from pypdf import PdfReader',
      `reader = PdfReader(${JSON.stringify(file)})`,
      "print(json.dumps({'pages': len(reader.pages), 'images': len(reader.pages[0].images), 'text': reader.pages[1].extract_text()}))",
    ].join('\n'),
  );
  return JSON.parse(read.split('\n').at(-1) as string);
}

test('FISCAL-F06: the staff upload ERPlora\'s stamp, see it on the model a business receives, and remove it', async ({ page }) => {
  const errors = watchPageErrors(page);
  seed('seed');
  await signIn(page.request, REVIEWER);

  // While there is none, the queue says so and leads to the stamp's page.
  await page.goto('/admin/fiscal/representationgrant/');
  await expect(page.locator('.messagelist')).toContainText("ERPlora's stamp and signature are not uploaded");
  await page.getByRole('link', { name: "Representative's stamp" }).click();
  await expect(page.getByRole('heading', { name: "Representative's stamp" })).toBeVisible();
  const missing = page.locator('.errornote', { hasText: 'No stamp uploaded' });
  await atEverySize(page, 'FISCAL-F06-empty', async () => {
    await expect(missing).toBeVisible();
  });
  const model = page.getByRole('link', { name: 'Download the model a business receives' });
  const modelHref = (await model.getAttribute('href')) as string;
  const without = await modelShape(page, modelHref, 'APP-FISCAL_GATEWAY-FISCAL-F06-without');
  expect(without.pages).toBe(2);
  // The second page is the RGPD sheet (art. 13) the model's «TRATAMIENTO DE DATOS» promises.
  expect(without.text).toContain('art. 13 RGPD');

  // A file that is not a PNG is refused on the page, and nothing is kept.
  const file = page.locator('#stamp-file');
  await file.setInputFiles({ name: 'stamp.png', mimeType: 'image/png', buffer: Buffer.from('not an image') });
  await page.getByRole('button', { name: 'Upload', exact: true }).click();
  await expect(page.locator('.messagelist')).toContainText('The stamp must be a PNG image.');
  await expect(missing).toBeVisible();

  await file.setInputFiles({ name: 'stamp.png', mimeType: 'image/png', buffer: syntheticStamp() });
  await page.getByRole('button', { name: 'Upload', exact: true }).click();
  await expect(page.locator('.messagelist')).toContainText('Stamp uploaded: every model downloaded from now on carries it.');
  const preview = page.getByRole('img', { name: "ERPlora's stamp and signature" });
  await atEverySize(page, 'FISCAL-F06', async () => {
    await expect(preview).toBeVisible();
    expect(await preview.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth)).toBe(320);
    await expect(page.getByRole('heading', { name: 'Replace the stamp' })).toBeVisible();
  });
  // The model now carries one image more on its first page: the stamp, in the representative's box.
  const stamped = await modelShape(page, modelHref, 'APP-FISCAL_GATEWAY-FISCAL-F06-with');
  expect(stamped.pages).toBe(2);
  expect(stamped.images).toBe(without.images + 1);
  // The queue no longer warns.
  await page.goto('/admin/fiscal/representationgrant/');
  await expect(page.locator('.messagelist')).toHaveCount(0);

  // Removing asks for the box to be ticked, then the models go without it again.
  await page.getByRole('link', { name: "Representative's stamp" }).click();
  await page.getByRole('checkbox', { name: /Yes, remove it/ }).check();
  await page.getByRole('button', { name: 'Remove the stamp' }).click();
  await expect(page.locator('.messagelist')).toContainText('Stamp removed: the models go without it until another is uploaded.');
  await expect(missing).toBeVisible();
  expect((await modelShape(page, modelHref, 'APP-FISCAL_GATEWAY-FISCAL-F06-removed')).images).toBe(without.images);
  expect(errors).toEqual([]);
});
