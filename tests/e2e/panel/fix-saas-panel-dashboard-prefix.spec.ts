// FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX in Chrome: the panel lives under /dashboard/, as the old product's
// `apps/dashboard/`. «Go to the panel» of the launcher lands on /dashboard/businesses (HUBS-F10), each entry of the menu
// opens its page under /dashboard/, /dashboard itself is Businesses, and an address of the panel at the root (a bookmark,
// a link of the Hub, a mail already sent) lands on the same page under /dashboard/ with its query. Accounts of
// panel_seed.py; at 390, 834 and 1440 px.
// flow: HUBS-F10
import {
  businessIdOf,
  expect,
  panelAccount,
  seedPanel,
  settled,
  shot,
  sidewaysScroll,
  signIn,
  test,
  VIEWPORTS,
  watchPageErrors,
} from './fixtures';

const KEY = 'FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX';

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('HUBS-F10 · «Go to the panel» lands on /dashboard/businesses and each entry of the menu opens its page under /dashboard/, at 390, 834 and 1440 px', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('several'));

  for (const size of VIEWPORTS) {
    await page.setViewportSize(size);
    await page.goto('/launch');
    await expect(page.getByRole('heading', { name: 'Where are you working today?' })).toBeVisible();
    await page.getByTestId('launch-panel').click();
    await expect(page).toHaveURL(/\/dashboard\/businesses$/);
    await expect(page.getByTestId('businesses-row').first()).toBeVisible();
    await settled(page);
    expect(await sidewaysScroll(page), `scrolls sideways at ${size.width}`).toEqual([]);
    await page.screenshot({ path: shot(`${KEY}-${size.width}`), fullPage: true });
  }

  // The menu's entries (the same at every size; at 1440 the side menu is always on screen): each opens its page.
  await page.setViewportSize({ width: 1440, height: 900 });
  const entries = page.locator('ion-menu .nav-item');
  await expect(entries).toHaveText(['Businesses', 'Store', 'Billing', 'Account']);
  for (const [label, path] of [
    ['Store', /\/dashboard\/store\/plans$/],
    ['Billing', /\/dashboard\/billing\/invoices$/],
    ['Account', /\/dashboard\/account\/profile$/],
    ['Businesses', /\/dashboard\/businesses$/],
  ] as const) {
    await entries.filter({ hasText: label }).click();
    await expect(page, label).toHaveURL(path);
    await expect(page.locator('ion-menu .nav-item[aria-current="page"]')).toHaveText(label);
  }
  expect(errors).toEqual([]);
});

test('HUBS-F10 · /dashboard is Businesses, and an address of the panel at the root lands on its page under /dashboard/ with its query', async ({
  page,
}) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('several'));
  const cafe = await businessIdOf(page.request, 'Café Central');

  for (const bare of ['/dashboard', '/dashboard/']) {
    const answer = await page.request.get(bare, { maxRedirects: 0 });
    expect([answer.status(), answer.headers().location], bare).toEqual([301, '/dashboard/businesses']);
  }
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/dashboard\/businesses$/);
  await expect(page.getByTestId('businesses-row').first()).toBeVisible();

  // The Hub's «Upgrade plan» and the mails link to the old addresses: one hop, the query kept.
  const old = `/store/plans?business=${cafe}`;
  const moved = await page.request.get(old, { maxRedirects: 0 });
  expect([moved.status(), moved.headers().location]).toEqual([301, `/dashboard/store/plans?business=${cafe}`]);
  await page.goto(old);
  await expect(page).toHaveURL(`/dashboard/store/plans?business=${cafe}`);
  await expect(page.getByTestId('store-plans')).toBeVisible();

  for (const [from, to] of [
    ['/businesses', /\/dashboard\/businesses$/],
    [`/businesses/${cafe}/members`, new RegExp(`/dashboard/businesses/${cafe}/members$`)],
    ['/account/security', /\/dashboard\/account\/security$/],
    ['/billing', /\/dashboard\/billing\/invoices$/],
    ['/report-a-problem', /\/dashboard\/report-a-problem$/],
  ] as const) {
    await page.goto(from);
    await expect(page, from).toHaveURL(to);
  }
  // The page itself, not the shell's «not found».
  await expect(page.getByTestId('report-subject')).toBeVisible();
  expect(errors).toEqual([]);
});
