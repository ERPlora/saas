// flow: HUBS-F29
// Members of a business on Free with four people, in Chrome: the places of the plan sit under the table, so at
// 1440×900 the four rows miss fitting by a few pixels. The rows' box still reaches the pager (no empty band) and the
// fourth person is on screen, cut at the pager only by what does not fit; before, the box stopped after the third
// row and left a band where the fourth one was. Screenshots at the three sizes, as a person sees the page.
import type { Page } from '@playwright/test';

import { panelAccount } from './accounts';
import { businessIdOf, seedPanel } from './businesses';
import { expect, test } from './fixtures';
import { watchPageErrors } from './page-events';
import { settled, shot, VIEWPORTS } from './screen';
import { apiPost, signIn } from './session';

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

/** Where the rows' box ends, where the pager starts and where the last row's name ends, in px from the top. */
async function rowsAndPager(page: Page): Promise<{ boxBottom: number; pagerTop: number; lastNameBottom: number }> {
  return page.evaluate(() => {
    const box = document.querySelector<HTMLElement>('.data-table--fill .data-table__scroll');
    const pager = document.querySelector<HTMLElement>('.data-table--fill .data-table__pager');
    const names = document.querySelectorAll<HTMLElement>('.data-table--fill .data-table__row--data .member-name');
    const last = names[names.length - 1];
    if (!box || !pager || !last) throw new Error('no filled list with its pager and its rows on screen');
    return {
      boxBottom: box.getBoundingClientRect().bottom,
      pagerTop: pager.getBoundingClientRect().top,
      lastNameBottom: last.getBoundingClientRect().bottom,
    };
  });
}

test('four people on Free at 1440×900: the four rows show and their box reaches the pager', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('free'));
  const id = await businessIdOf(page.request, 'Frutería Sol');
  // The owner, two employees (the plan's three places) and the accountancy firm, which takes none.
  for (const [n, role] of [[1, 'hub_employee'], [2, 'hub_employee'], [3, 'hub_accountant']] as const) {
    const invited = await apiPost(page.request, '/api/hubs/members/invite', { hub_id: id, email: `e2e-fourth-${n}@example.com`, role, message: '' });
    expect(invited.status(), await invited.text()).toBe(200);
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/dashboard/businesses/${id}/members`);
  await expect(page.getByTestId('members-row')).toHaveCount(4);
  await expect(page.getByTestId('members-seats')).toBeVisible();
  await settled(page);
  const { boxBottom, pagerTop, lastNameBottom } = await rowsAndPager(page);
  expect(Math.abs(pagerTop - boxBottom), 'an empty band between the rows and the pager').toBeLessThanOrEqual(1);
  expect(lastNameBottom, 'the fourth person is hidden under the bottom of the rows').toBeLessThanOrEqual(boxBottom);

  for (const size of VIEWPORTS) {
    await page.setViewportSize(size);
    await expect(page.getByTestId('members-row')).toHaveCount(4);
    await settled(page);
    await page.screenshot({ path: shot(`members-four-people-${size.width}`) });
  }
  expect(errors).toEqual([]);
});
