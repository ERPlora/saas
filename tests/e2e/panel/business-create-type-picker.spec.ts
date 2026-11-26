// flow: HUBS-F01
// The «Business type (optional)» of creating a business, in Chrome: the start's «Create your business» and the dialog of
// Businesses share it. In English and in Spanish its list reads «I don't know yet» first and then every type in
// alphabetical order of the person's language; typing filters it, so on a tablet held sideways (1280×665) the type is
// found on screen without scrolling the list. At every size the list stays inside the window.
import { type Page } from '@playwright/test';

import { createAccountWarm, removeAccountsWarm } from './accounts';
import { readyBusinessOn } from './businesses';
import { djangoPrintWarm } from './django';
import { expect, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { catalogueText, settled, shot } from './screen';
import { signIn } from './session';

const PREFIX = 'e2e-type-picker-';
const PASSWORD = 'Masa-madre-y-centeno-26';
const SIDEWAYS_TABLET = { width: 1280, height: 665 };
const SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1280, height: 720 },
] as const;
const LANGUAGES = [
  { language: 'en', locale: 'en-US', typed: 'hair', found: 'Hair Salon' },
  { language: 'es', locale: 'es-ES', typed: 'pelu', found: 'Peluquería' },
] as const;

test.beforeAll(async () => {
  await removeAccountsWarm(PREFIX);
  // The taxonomy every deploy seeds (saas-migrate runs seed_taxonomy): the same here.
  await djangoPrintWarm('from django.core.management import call_command\ncall_command("seed_taxonomy")');
});
test.afterAll(() => removeAccountsWarm(PREFIX));

/** The server's alphabetical key: accents and capitals do not move a name. */
const fold = (name: string): string => name.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
const byName = (a: string, b: string): number => (fold(a) < fold(b) ? -1 : fold(a) > fold(b) ? 1 : 0);

interface ShownList {
  labels: string[];
  /** Options whole inside the list's box and the window, without scrolling the list. */
  inView: string[];
  /** How far the list's box reaches past the window, at its top and at its bottom. */
  past: number;
}

/** The open list of the type field: its options, those on screen, and whether it stays inside the window. */
function shownList(page: Page): Promise<ShownList> {
  return page.evaluate(() => {
    const listbox = document.querySelector<HTMLElement>('ion-popover [role="listbox"]');
    if (!listbox) return { labels: [], inView: [], past: Number.POSITIVE_INFINITY };
    const box = listbox.closest('ion-popover')!.shadowRoot!.querySelector<HTMLElement>('[part~="content"]')!.getBoundingClientRect();
    const options = [...listbox.querySelectorAll<HTMLElement>('[role="option"]')];
    const inView = options.filter((option) => {
      const rect = option.getBoundingClientRect();
      return rect.top >= Math.max(box.top, 0) - 1 && rect.bottom <= Math.min(box.bottom, window.innerHeight) + 1;
    });
    const text = (option: HTMLElement) => option.textContent!.replace(/\s+/g, ' ').trim();
    return {
      labels: options.map(text),
      inView: inView.map(text),
      past: Math.max(0, Math.ceil(-box.top), Math.ceil(box.bottom - window.innerHeight)),
    };
  });
}

async function openTypeList(page: Page): Promise<ShownList> {
  await page.getByTestId('create-type').click();
  await expect(page.locator('ion-popover [role="option"]').first()).toBeVisible();
  await settled(page);
  return shownList(page);
}

/** Types the start of a type, takes the first option and leaves it in the field. */
async function findByTyping(page: Page, typed: string, found: string, where: string): Promise<void> {
  await page.getByTestId('create-type').locator('input').fill(typed);
  await settled(page);
  const list = await shownList(page);
  expect(list.labels[0], `${where}: «${typed}» leads with its type`).toBe(found);
  expect(list.inView, `${where}: the type found is on screen`).toContain(found);
  await page.getByRole('option', { name: found }).click();
  await expect(page.locator('ion-popover [role="listbox"]')).toHaveCount(0);
  await expect(page.getByTestId('create-type').locator('input')).toHaveValue(found);
}

for (const { language, locale, typed, found } of LANGUAGES) {
  test.describe(`in ${language}`, () => {
    test.use({ locale });

    test('the business type: «I don’t know yet» first, then by name, found by typing on a sideways tablet', async ({ page }) => {
      const errors = watchPageErrors(page);
      const unknown = catalogueText('hubs', language, 'hubs.create.typeUnknown');
      const email = `${PREFIX}${language}-${Date.now()}@example.com`;
      await createAccountWarm(email, PASSWORD, { language, firstName: 'Ana', lastName: 'López' });
      await signIn(page.request, { email, password: PASSWORD });

      await page.setViewportSize(SIDEWAYS_TABLET);
      await page.goto('/launch');
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      const atStart = await openTypeList(page);
      expect(atStart.labels[0]).toBe(unknown);
      expect(atStart.labels.length).toBeGreaterThan(60);
      expect(atStart.labels.slice(1)).toEqual([...atStart.labels.slice(1)].sort(byName));
      expect(atStart.past, 'the list stays inside the window').toBe(0);
      expect(atStart.inView.length, 'options on screen at once on a sideways tablet').toBeGreaterThanOrEqual(6);
      await page.screenshot({ path: shot(`business-create-type-launch-${language}-1280x665`) });
      await findByTyping(page, typed, found, 'the start');

      await readyBusinessOn(page.request, language === 'es' ? 'Bar Uno' : 'Corner Bar', 'starter');
      await page.goto('/dashboard/businesses?create=1');
      await expect(page.getByTestId('create-modal')).toContainText(catalogueText('hubs', language, 'hubs.create.heading'));
      const inDialog = await openTypeList(page);
      expect(inDialog.labels).toEqual(atStart.labels);
      expect(inDialog.past, 'the list stays inside the window').toBe(0);
      expect(inDialog.inView.length, 'options on screen at once on a sideways tablet').toBeGreaterThanOrEqual(6);
      await page.screenshot({ path: shot(`business-create-type-dialog-${language}-1280x665`) });
      await findByTyping(page, typed, found, 'the dialog');

      for (const size of SIZES) {
        await page.setViewportSize(size);
        await settled(page);
        const list = await openTypeList(page);
        expect(list.past, `the list stays inside the window at ${size.width}×${size.height}`).toBe(0);
        expect(list.inView.length, `options on screen at ${size.width}×${size.height}`).toBeGreaterThanOrEqual(4);
        await page.screenshot({ path: shot(`business-create-type-dialog-${language}-${size.width}x${size.height}`) });
        await page.keyboard.press('Escape');
        await expect(page.locator('ion-popover [role="listbox"]')).toHaveCount(0);
      }
      expect(errors).toEqual([]);
    });
  });
}
