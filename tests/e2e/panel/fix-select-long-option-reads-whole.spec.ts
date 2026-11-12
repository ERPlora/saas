// In the panel too, a long option of a dropdown reads whole before it is chosen, on as many lines as it takes.
// The rule is the shared theme's (@erplora/ui, polish.css), measured in detail by the Hub's
// tests/e2e/fix-ui-select-long-option-reads-whole.spec.ts; this says it reaches the panel, on the time zones of a
// business's settings at 320, where the longest names need their second line: each label against its own box, never a capture.
// flow: HUBS-F15
import {
  apiPost,
  expect,
  internalSecret,
  panelAccount,
  reportBusinessReady,
  seedPanel,
  settled,
  shot,
  signIn,
  test,
  watchPageErrors,
} from './fixtures';

const NAME = 'Zonas Largas E2E';

test.beforeAll(async () => {
  seedPanel();
  // The Hub's callback signs with it: read here, so that its Django boot is on no test's clock (saas#346).
  await internalSecret();
});
test.afterAll(() => seedPanel('clear'));

test('HUBS-F15: every time zone reads whole in its list at 320x568', async ({ page }) => {
  const errors = watchPageErrors(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await signIn(page.request, panelAccount('creator'));
  const created = await apiPost(page.request, '/api/hubs/businesses', { name: NAME, country: 'ES' });
  expect(created.status(), 'POST /api/hubs/businesses').toBe(201);
  const { id } = (await created.json()) as { id: string };
  // Ready by the Hub's own callback, signed (here no Hub answers): no Python inside the test (saas#355).
  await reportBusinessReady(page.request, id);
  await page.goto(`/dashboard/businesses/${id}/settings`);
  await page.getByTestId('settings-timezone').click();
  await expect(page.locator('ion-select-popover ion-radio').first()).toBeVisible();
  await settled(page);

  const options = await page.locator('ion-select-popover ion-radio').evaluateAll((radios) =>
    radios.map((radio) => {
      const label = radio.shadowRoot!.querySelector<HTMLElement>('[part~="label"]')!;
      return { text: radio.textContent!.trim(), past: label.scrollWidth - label.clientWidth, height: label.clientHeight };
    }),
  );
  expect(options.length).toBeGreaterThan(1);
  expect(options.filter((option) => option.past > 0).map((option) => `${option.text}: ${option.past}px past its width`)).toEqual([]);
  const oneLine = Math.min(...options.map((option) => option.height));
  expect(options.filter((option) => option.height > oneLine).length).toBeGreaterThan(0);
  await page.screenshot({ path: shot('FIX-SELECT-LONG-OPTION-320') });
  expect(errors).toEqual([]);
});
