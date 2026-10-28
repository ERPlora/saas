// flow: ninguno — arnés e2e del SaaS (límites de allauth con la marca de e2e)
// The e2e's panel server raises allauth's limits per address (E2E_RELAX_LOGIN_RATE_LIMIT, project.ts and
// config/settings.py), the sign-up's included: every spec creates its accounts from 127.0.0.1, and with the real
// 10 sign-ups an hour per address the eleventh «Create account» of a run got «Too many attempts» (429). Production
// and the dev server keep the 10 (config/tests/test_production_settings.py). Accounts of this spec:
// `e2e-signup-limit-<n>-<time>@example.com`, removed before and after.
import { djangoPrint, expect, settled, shot, sidewaysScroll, submitSignInForm, test, VIEWPORTS, watchPageErrors } from './fixtures';

/** allauth.headless's sign-up for the browser client: what the launcher's «Create account» posts. */
const SIGN_UP_API = '/_allauth/browser/v1/auth/signup';
/** allauth's sign-up limit per address everywhere but in the e2e's panel server (config/settings.py). */
const SIGN_UPS_AN_HOUR = 10;
const PASSWORD = 'Signup-e2e-2026!';

const ACCOUNTS = 'get_user_model().objects.filter(email__startswith="e2e-signup-limit-", email__endswith="@example.com")';

function removeAccounts(): void {
  djangoPrint(['from django.contrib.auth import get_user_model', `${ACCOUNTS}.delete()`].join('\n'));
}

test.beforeAll(removeAccounts);
test.afterAll(removeAccounts);

test('more than ten «Create account» from one address in a run: the eleventh still waits for its mailed code', async ({
  page,
  playwright,
  baseURL,
}) => {
  const errors = watchPageErrors(page);
  const run = Date.now();
  const email = (n: number): string => `e2e-signup-limit-${n}-${run}@example.com`;

  // allauth's own limit, reached through its API: each sign-up from a browser of its own, all from 127.0.0.1.
  for (let n = 1; n <= SIGN_UPS_AN_HOUR; n += 1) {
    const visitor = await playwright.request.newContext({ baseURL });
    try {
      expect((await visitor.get('/launch')).status(), 'GET /launch').toBe(200);
      const { cookies } = await visitor.storageState();
      const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
      const response = await visitor.post(SIGN_UP_API, { headers: { 'X-CSRFToken': csrf }, data: { email: email(n), password: PASSWORD } });
      const answer = (await response.json()) as { data?: { flows?: Array<{ id: string; is_pending?: boolean }> } };
      const pending = answer.data?.flows?.filter((flow) => flow.is_pending).map((flow) => flow.id);
      expect([response.status(), pending], `sign-up ${n}: ${JSON.stringify(answer)}`).toEqual([401, ['verify_email']]);
    } finally {
      await visitor.dispose();
    }
  }

  // One more, as a person does on the launcher: the code's page, never «Too many attempts».
  const eleventh = email(SIGN_UPS_AN_HOUR + 1);
  await page.goto('/launch?tab=signup');
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await submitSignInForm(page, { email: eleventh, password: PASSWORD });
  await expect(page).toHaveURL(/\/verify-email$/);
  await expect(page.getByText(`We emailed a code to ${eleventh}`)).toBeVisible();
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await settled(page);
    expect(await sidewaysScroll(page), `/verify-email scrolls sideways at ${viewport.width} px`).toEqual([]);
    await page.screenshot({ path: shot(`FIX-SAAS-E2E-SIGNUP-RATELIMIT-NOT-RELAXED-${viewport.width}`), fullPage: true });
  }

  expect(
    djangoPrint(['from django.contrib.auth import get_user_model', `print(${ACCOUNTS}.filter(email__contains="-${run}@").count())`].join('\n')),
  ).toBe(String(SIGN_UPS_AN_HOUR + 1));
  expect(errors).toEqual([]);
});
