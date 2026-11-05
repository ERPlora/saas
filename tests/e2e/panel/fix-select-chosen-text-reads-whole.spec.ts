// saas#272 — what a form's dropdown has chosen reads whole with the field closed, on as many lines as it takes: at 320
// a business's «Time zone» read «Madrid (Central European …» and the store's «Business» cut a long name at any phone
// width. The rule is the shared theme's (@erplora/ui, polish.css), for the outlined selects of a form; each field is
// measured here against its own box, never a capture, and with what it holds: the zones and a name as long as allowed.
// flow: HUBS-F15
// flow: BILLING-F08
import { type APIRequestContext, type Locator, type Page } from '@playwright/test';

import { apiPost, businessIdOf, djangoPrint, expect, panelAccount, seedPanel, settled, shot, sidewaysScroll, signIn, test, watchPageErrors } from './fixtures';

/** As long as `hubs.schemas.Name` admits (120), in words a line can break at. */
const LONG_NAME = 'Panadería y Pastelería Artesana de la Plaza Mayor de Santa María del Campo y Alrededores, Obrador Tradicional de Masa de';
const SIZES = [
  { width: 320, height: 568 },
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1440, height: 900 },
] as const;

interface Field {
  text: string;
  /** How far the text runs past its own box, sideways and downwards: what `overflow: hidden` cuts. */
  pastWidth: number;
  pastHeight: number;
  /** How far the painted text runs past the outlined box of the field. */
  pastField: number;
  /** How far the first line climbs into the label floating on the field's edge. */
  overLabel: number;
}

/** What the closed `select` paints (run in the page, so self-contained). */
function readField(select: HTMLElement): Field {
  const text = select.shadowRoot!.querySelector<HTMLElement>('[part~="text"]')!;
  const range = document.createRange();
  range.selectNodeContents(text);
  const painted = range.getBoundingClientRect();
  const box = select.getBoundingClientRect();
  const label = select.shadowRoot!.querySelector<HTMLElement>('[part~="label"]')!.getBoundingClientRect();
  return {
    text: text.textContent!.trim(),
    pastWidth: text.scrollWidth - text.clientWidth,
    pastHeight: text.scrollHeight - text.clientHeight,
    pastField: Math.ceil(Math.max(painted.right - box.right, painted.bottom - box.bottom, box.left - painted.left, box.top - painted.top)),
    overLabel: Math.ceil(label.bottom - painted.top),
  };
}

const cut = (field: Field): boolean => field.pastWidth > 0 || field.pastHeight > 0 || field.pastField > 0 || field.overLabel > 0;
const said = (field: Field): string =>
  `${field.text}: ${field.pastWidth}px sideways, ${field.pastHeight}px down, ${field.pastField}px out of the field, ${field.overLabel}px into the label`;

/** Two frames, so that what a change asks for has been painted. */
const painted = (select: Locator) =>
  select.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));

/** The closed field with each of its options chosen, as `select.value` leaves it; then back to what it had. */
async function everyOption(select: Locator): Promise<Field[]> {
  const had = await select.evaluate((field) => (field as HTMLElement & { value: unknown }).value);
  const options = await select.locator('ion-select-option').evaluateAll((all) => all.map((option) => (option as HTMLElement & { value: unknown }).value));
  const choose = async (value: unknown) => {
    await select.evaluate((field, chosen) => {
      (field as HTMLElement & { value: unknown }).value = chosen;
    }, value);
    await painted(select);
  };
  const seen: Field[] = [];
  for (const option of options) {
    await choose(option);
    seen.push(await select.evaluate(readField));
  }
  await choose(had);
  return seen;
}

/** The account's business, ready as the Hub's callback leaves it (here no Hub answers), with a name as long as allowed. */
async function business(request: APIRequestContext): Promise<string> {
  const created = await apiPost(request, '/api/hubs/businesses', { name: LONG_NAME, country: 'ES' });
  const id = created.status() === 201 ? ((await created.json()) as { id: string }).id : await businessIdOf(request, LONG_NAME);
  djangoPrint(
    [
      'from django.utils import timezone',
      'from hubs.models import Hub',
      `Hub.objects.filter(pk="${id}").update(status="active", ready_at=timezone.now())`,
    ].join('\n'),
  );
  return id;
}

/** The seeded account signed in, speaking `lang` (the seed leaves it in English), and the id of its business. */
async function signedInWithBusiness(page: Page, lang = 'en'): Promise<string> {
  const account = panelAccount('creator');
  djangoPrint(
    [
      'from django.contrib.auth import get_user_model',
      `get_user_model().objects.filter(email="${account.email}").update(language="${lang}")`,
    ].join('\n'),
  );
  await signIn(page.request, account);
  return business(page.request);
}

const atSize = async (page: Page, size: (typeof SIZES)[number]) => {
  await page.setViewportSize(size);
  await settled(page);
};

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

for (const lang of ['en', 'es']) {
  test.describe(lang, () => {
    test(`HUBS-F15: every time zone reads whole in the closed field, at each size, in ${lang}`, async ({ page }) => {
      const errors = watchPageErrors(page);
      const id = await signedInWithBusiness(page, lang);
      await page.goto(`/dashboard/businesses/${id}/settings`);
      const zone = page.getByTestId('settings-timezone');
      await expect(zone).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', lang);

      for (const size of SIZES) {
        await atSize(page, size);
        const chosen = await zone.evaluate(readField);
        expect(chosen.text, 'the zone the business has').toContain('Madrid (');
        expect(cut(chosen) ? [`${size.width}: ${said(chosen)}`] : []).toEqual([]);
        const zones = await everyOption(zone);
        expect(zones.length).toBeGreaterThan(1);
        expect(zones.filter(cut).map((field) => `${size.width}: ${said(field)}`)).toEqual([]);
        // What fits on one line keeps the height of every other field of the form.
        expect(await page.getByTestId('settings-language').evaluate((language) => language.getBoundingClientRect().height), `one line at ${size.width}`).toBe(56);
        expect(await sidewaysScroll(page), `sideways at ${size.width}`).toEqual([]);
        await zone.scrollIntoViewIfNeeded();
        await page.screenshot({ path: shot(`FIX-SELECT-CHOSEN-TEXT-${lang}-${size.width}`) });
      }
      expect(errors).toEqual([]);
    });
  });
}

test('HUBS-F15: the zone a person picks in the list reads whole once the list has closed, at 320x568', async ({ page }) => {
  const errors = watchPageErrors(page);
  const id = await signedInWithBusiness(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto(`/dashboard/businesses/${id}/settings`);
  const zone = page.getByTestId('settings-timezone');
  await zone.click();
  const longest = page.locator('ion-select-popover ion-radio').filter({ hasText: 'Copenhagen' });
  await expect(longest).toBeVisible();
  await settled(page);
  await longest.click();
  await expect(page.locator('ion-select-popover')).toHaveCount(0);
  await settled(page);
  const chosen = await zone.evaluate(readField);
  expect(chosen.text).toContain('Copenhagen');
  expect(cut(chosen) ? [said(chosen)] : []).toEqual([]);
  await page.screenshot({ path: shot('FIX-SELECT-CHOSEN-TEXT-PICKED-320') });
  expect(errors).toEqual([]);
});

test('BILLING-F08: the business the store is for reads whole with the longest name, at each size', async ({ page }) => {
  const errors = watchPageErrors(page);
  const id = await signedInWithBusiness(page);
  await page.setViewportSize(SIZES[0]);
  await page.goto(`/dashboard/store/plans?business=${id}`);
  const picker = page.getByTestId('store-business');
  await expect(picker).toBeVisible();
  for (const size of SIZES) {
    await atSize(page, size);
    const chosen = await picker.evaluate(readField);
    expect(chosen.text).toContain(LONG_NAME);
    expect(cut(chosen) ? [`${size.width}: ${said(chosen)}`] : []).toEqual([]);
    expect(await sidewaysScroll(page), `sideways at ${size.width}`).toEqual([]);
    await picker.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot(`FIX-SELECT-CHOSEN-TEXT-STORE-${size.width}`) });
  }
  expect(errors).toEqual([]);
});
