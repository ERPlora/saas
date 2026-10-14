// The invitation (`/invitation`, mockups `invitation.html`) in Ioan's Chrome: the pending invitations
// with who invites and as what; «Decline» confirms and the invitation is gone («no longer valid»);
// «Accept and enter» goes to the business's Hub, its start of the jump (answered by the spec, no Hub runs).
import { expect, panelAccount, seedPanel, signIn, test, watchPageErrors } from './fixtures';

test.beforeAll(() => seedPanel());
test.afterAll(() => seedPanel('clear'));

test('«Decline» asks first; then the invitation is no longer valid', async ({ page }) => {
  const errors = watchPageErrors(page);
  await signIn(page.request, panelAccount('several'));
  await page.goto('/invitation');
  await expect(page.getByRole('heading', { name: 'You have been invited' })).toBeVisible();
  const card = page.locator('.invite-card').filter({ hasText: 'Bar Norte' });
  await expect(card).toContainText('Carlos Ruiz invites you · Employee');
  await card.getByTestId('invitation-decline').click();
  await expect(page.getByTestId('decline-dialog')).toContainText('Carlos Ruiz invited you to Bar Norte.');
  await page.getByTestId('decline-dialog-submit').click();
  await expect(page.getByRole('heading', { name: 'This invitation is no longer valid' })).toBeVisible();
  await expect(page.getByTestId('invitation-expired')).toContainText('e2e-several@example.com');
  expect(errors).toEqual([]);
});

test('«Accept and enter» goes into the business', async ({ page }) => {
  const errors = watchPageErrors(page);
  const visits: string[] = [];
  await page.route(/^http:\/\/[\w-]+\.localhost:8000\//, async (route) => {
    visits.push(`${route.request().method()} ${route.request().url()}`);
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<h1>Hub</h1>' });
  });
  await signIn(page.request, panelAccount('invited'));
  await page.goto('/invitation');
  await page.getByTestId('invitation-accept').click();
  await expect.poll(() => visits).toEqual(['GET http://e2e-peluqueria-ana.localhost:8000/auth/login?next=/']);
  expect(errors).toEqual([]);
});
