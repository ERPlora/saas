// A confirmation (ui:ConfirmDialog, a centred card at every width) stays whole on screen when the window changes size
// under it: a desktop window narrowed to a phone and back, and a tablet turned both ways. Seen once in the Hub,
// capturing «Deactivate» of a price list at 1280×860 and then 390×844, and never reproduced since, in the Hub or
// here, in Ionic's `ios` or `md`: this spec is what keeps it from coming back. Two confirmations of the panel, in
// English and in Spanish: «Delete business» at the end of the business's Settings (the page scrolls to it; a tall
// confirmation, with the name to type) and «Close the other sessions» in Security (a short one).
// The card is Ionic's `.modal-wrapper` (its shadow DOM): once the page has settled it is inside the window and opaque.
// A card that lost its enter animation rests where Ionic parks it before the enter, its own height lower in `ios` (out
// of a phone's window for «Delete business») and almost transparent in `md`, and fails here.
// flow: ui:ConfirmDialog
import { type Page } from '@playwright/test';

import {
  catalogueText,
  createAccountWarm,
  expect,
  internalSecret,
  readyBusinessOn,
  removeAccountsWarm,
  settled,
  signIn,
  test,
} from './fixtures';
import { PANEL_URL } from './project';

const PREFIX = 'e2e-confirm-in-view-';
const PASSWORD = 'Masa-madre-y-centeno-26';
const BUSINESS = 'Bar Manolo';

/** Each walk opens the dialog at its first size and, without closing it, gives the window the next ones. */
const WALKS = [
  [
    { width: 1280, height: 860 },
    { width: 390, height: 844 },
    { width: 1280, height: 860 },
  ],
  [
    { width: 834, height: 1112 },
    { width: 1112, height: 834 },
    { width: 834, height: 1112 },
  ],
  [
    { width: 1112, height: 834 },
    { width: 834, height: 1112 },
  ],
] as const;

/** `'whole'` while the open dialog's card is inside the window and opaque; otherwise where it is. */
function cardOnScreen(page: Page): Promise<string> {
  return page.evaluate(() => {
    const modal = [...document.querySelectorAll<HTMLElement>('ion-modal.ep-form-modal.show-modal')].at(-1);
    const card = modal?.shadowRoot?.querySelector<HTMLElement>('.modal-wrapper');
    if (!card) return 'no dialog open';
    const { left, top, right, bottom } = card.getBoundingClientRect();
    const opacity = Number(getComputedStyle(card).opacity);
    const inside = left >= -0.5 && top >= -0.5 && right <= innerWidth + 0.5 && bottom <= innerHeight + 0.5;
    if (inside && opacity > 0.99) return 'whole';
    return JSON.stringify({ left, top, right, bottom, opacity, window: `${innerWidth}×${innerHeight}` });
  });
}

/** The walks over the dialog `testid` (titled `title`), which `open` opens: at every size its card stays whole. */
async function staysInView(page: Page, testid: string, title: string, open: () => Promise<void>): Promise<void> {
  for (const [first, ...next] of WALKS) {
    await page.setViewportSize(first);
    await settled(page);
    await open();
    await expect(page.getByTestId(testid)).toContainText(title);
    for (const size of [first, ...next]) {
      await page.setViewportSize(size);
      await settled(page);
      await expect
        .poll(() => cardOnScreen(page), { message: `«${testid}» opened at ${first.width}×${first.height}, at ${size.width}×${size.height}` })
        .toBe('whole');
      await expect(page.getByTestId(`${testid}-submit`)).toBeInViewport({ ratio: 1 });
    }
    await page.getByTestId(`${testid}-cancel`).click();
    await expect(page.locator('ion-modal.ep-form-modal.show-modal')).toHaveCount(0);
  }
}

/** A fresh account of this spec in `language`, its address proven, signed in on `page`. */
async function signedUp(page: Page, who: string, language: 'en' | 'es'): Promise<{ email: string; password: string }> {
  const account = { email: `${PREFIX}${who}-${language}-${Date.now()}@example.com`, password: PASSWORD };
  await createAccountWarm(account.email, PASSWORD, { language });
  await signIn(page.request, account);
  return account;
}

// The warm Django and the secret of the Hub's callback, once here (saas#354).
test.beforeAll(async () => {
  await Promise.all([removeAccountsWarm(PREFIX), internalSecret()]);
});
test.afterAll(() => removeAccountsWarm(PREFIX));

for (const language of ['en', 'es'] as const) {
  test(`ui:ConfirmDialog — «Delete business», opened at the end of Settings, stays whole as the window changes (${language})`, async ({
    page,
  }) => {
    await signedUp(page, 'delete', language);
    const id = await readyBusinessOn(page.request, BUSINESS, 'free');
    await page.goto(`/dashboard/businesses/${id}/settings`);
    const remove = page.getByTestId('danger-delete');
    await expect(remove).toBeVisible();
    // How far Settings had scrolled down to «Delete business» each time it was opened: at 834×1112 the page fits.
    const scrolled: number[] = [];
    await staysInView(page, 'delete-dialog', catalogueText('hubs', language, 'hubs.danger.confirmTitle', { name: BUSINESS }), async () => {
      await remove.scrollIntoViewIfNeeded();
      scrolled.push(
        await remove.evaluate(async (button) => {
          const content = button.closest<HTMLElement & { getScrollElement(): Promise<HTMLElement> }>('ion-content');
          return content ? (await content.getScrollElement()).scrollTop : 0;
        }),
      );
      await remove.click();
    });
    expect(Math.max(...scrolled), `Settings scrolled down to «Delete business»: ${scrolled.join(', ')}`).toBeGreaterThan(0);
  });

  test(`ui:ConfirmDialog — «Close the other sessions» stays whole as the window changes (${language})`, async ({ page, browser }) => {
    const account = await signedUp(page, 'sessions', language);
    const other = await browser.newContext({ baseURL: PANEL_URL });
    try {
      await signIn(other.request, account);
      await page.goto('/dashboard/account/security');
      await expect(page.getByTestId('sessions-row')).toHaveCount(2);
      await staysInView(page, 'sessions-close-others-dialog', catalogueText('accounts', language, 'accounts.account.sessions.othersTitle'), () =>
        page.getByTestId('sessions-close-others').click(),
      );
    } finally {
      await other.close();
    }
  });
}
