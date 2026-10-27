// Creating a business (round 17 §2.3; mockups `businesses.html` «create»/«creating»/«create-ready») in
// Ioan's Chrome: the empty Businesses holds the sign-up form; the address follows the name; after
// «Create my business» the dialog shows the preparation and the row appears «Preparing» through the
// live list; when the Hub reports it ready (here the spec plays the Hub: a signed
// `POST /internal/hubs/{id}/ready`, as hub-next sends it) the dialog says it is ready and the row is
// «Active». The panel's Django (project.ts) sends its calls to the Hub nowhere: a Hub running locally
// never provisions this throwaway business (no orphan database), and the SaaS keeps the registry
// pending as when the Hub is away.
import { createHmac } from 'node:crypto';

import { businessIdOf, expect, internalSecret, panelAccount, seedPanel, signIn, test, watchPageErrors } from './fixtures';
test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('create → Preparing → the Hub reports it ready → Ready', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('creator'));
  await page.goto('/dashboard/businesses');
  await expect(page.getByTestId('businesses-empty')).toContainText('Create your first business');

  await page.getByTestId('create-name').locator('input').fill('Pastelería Dulce E2E');
  await expect(page.getByTestId('create-address')).toContainText('Your address will be pasteleria-dulce-e2e');
  await page.getByTestId('create-submit').click();

  await expect(page.getByTestId('create-modal')).toContainText('Preparing Pastelería Dulce E2E');
  await expect(page.getByTestId('create-modal')).toContainText('Business created');
  const row = page.getByTestId('businesses-row').filter({ hasText: 'Pastelería Dulce E2E' });
  await expect(row).toContainText('Preparing');

  // The Hub's callback: the body names the hub of the path, signed with the shared secret.
  const id = await businessIdOf(page.request, 'Pastelería Dulce E2E');
  const body = JSON.stringify({ id });
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac('sha256', internalSecret()).update(`${timestamp}.${body}`).digest('hex');
  const ready = await page.request.post(`/internal/hubs/${id}/ready`, {
    data: body,
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': String(timestamp), 'X-Erplora-Signature': signature },
  });
  expect(ready.status(), await ready.text()).toBe(200);

  await expect(page.getByTestId('create-modal')).toContainText('Your business is ready');
  await expect(page.getByTestId('create-modal-open')).toBeVisible();
  await page.getByTestId('create-modal-close-list').click();
  await expect(row).toContainText('Active');
  expect(errors).toEqual([]);
});
