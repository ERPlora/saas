// flow: HUBS-F09
// Businesses with a long web address, in Chrome: at every size, in English and in Spanish, each address stays inside
// its column (or its card), also one with no hyphen to break at, and the «Status» column beside it reads whole, also on
// a tablet held sideways (1280×665).
import { type Page } from '@playwright/test';

import { createAccountWarm, removeAccountsWarm } from './accounts';
import { readyBusinessOn } from './businesses';
import { expect, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { settled, shot } from './screen';
import { apiPost, signIn } from './session';

const PREFIX = 'e2e-longhost-';
const PASSWORD = 'Masa-madre-y-centeno-26';
const ACTIVE = 'QA Restaurante 20261125-2101';
const DELETED = 'Peluquería QA Asistente';
const CHOSEN = 'Los Amigos del Puerto';
// The one-word address its owner chose for it: nowhere to break but inside the word.
const ONE_WORD = 'restaurantelosamigosdelpuerto';
const ADDRESS = /^(qa-restaurante-20261125-2101|peluqueria-qa-asistente|restaurantelosamigosdelpuerto)\S*\.\S+$/;
const SIZES = [
  { width: 1280, height: 665 },
  { width: 1280, height: 720 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
  { width: 1440, height: 900 },
] as const;

test.beforeAll(() => removeAccountsWarm(PREFIX));
test.afterAll(() => removeAccountsWarm(PREFIX));

/** Per address on screen, how far its text reaches past the box it is laid out in (its cell, or its card). */
function addressesPastTheirBox(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const found: string[] = [];
    for (const host of shown.querySelectorAll<HTMLElement>('[data-testid="business-host"]')) {
      const boxes = [host.closest('.data-table__cell'), host.closest('.data-table__card-meta-value'), host.closest('.data-table__card')]
        .filter((box): box is HTMLElement => box instanceof HTMLElement);
      if (boxes.length === 0) {
        found.push(`${host.textContent?.trim()}: in no cell nor card`);
        continue;
      }
      const edge = Math.min(...boxes.map((box) => box.getBoundingClientRect().right));
      const text = document.createRange();
      text.selectNodeContents(host);
      const right = Math.max(...[...text.getClientRects()].map((rect) => rect.right));
      if (right > edge + 0.5) found.push(`${host.textContent?.trim()}: ${Math.round(right - edge)} px past its box`);
    }
    return found;
  });
}

for (const { language, locale } of [
  { language: 'en', locale: 'en-US' },
  { language: 'es', locale: 'es-ES' },
] as const) {
  test.describe(`in ${language}`, () => {
    test.use({ locale });

    test('a long web address stays in its column and the status beside it reads whole', async ({ page }) => {
      const errors = watchPageErrors(page);
      const email = `${PREFIX}${language}-${Date.now()}@example.com`;
      await createAccountWarm(email, PASSWORD, { language, firstName: 'Ana', lastName: 'López' });
      await signIn(page.request, { email, password: PASSWORD });
      // Each business is born on Free, which an account holds once: all but the last move to a paid plan.
      const gone = await readyBusinessOn(page.request, DELETED, 'starter');
      const chosen = await readyBusinessOn(page.request, CHOSEN, 'pro');
      const moved = await apiPost(page.request, '/api/hubs/businesses/address', { id: chosen, slug: `${ONE_WORD}${language}` });
      expect(moved.status(), await moved.text()).toBe(200);
      await readyBusinessOn(page.request, ACTIVE, 'free');
      const deleted = await apiPost(page.request, '/api/hubs/businesses/delete', { id: gone, confirm_name: DELETED });
      expect(deleted.status(), await deleted.text()).toBe(200);

      await page.setViewportSize(SIZES[0]);
      await page.goto('/dashboard/businesses');
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      const hosts = page.getByTestId('business-host');
      await expect(hosts).toHaveCount(3);
      await expect(page.getByTestId('business-status-why')).toHaveCount(1);
      for (const host of await hosts.allTextContents()) expect(host.trim()).toMatch(ADDRESS);

      for (const size of SIZES) {
        await page.setViewportSize(size);
        await settled(page);
        expect(await addressesPastTheirBox(page), `an address leaves its box at ${size.width}×${size.height}`).toEqual([]);
        await page.screenshot({ path: shot(`hubs-list-long-address-${size.width}x${size.height}-${language}`) });
      }
      expect(errors).toEqual([]);
    });
  });
}
