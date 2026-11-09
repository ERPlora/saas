// saas#389 — the public footer's language buttons keep a 44x44 touch target with a coarse pointer. The shared
// Playwright configuration captures a screenshot and trace only when the measurement fails.
import { expect, test } from './public-test';

const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
];

test.use({ hasTouch: true, locale: 'en-GB' });

for (const viewport of VIEWPORTS) {
  test(`footer language targets are at least 44x44 at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto('/');
    const languages = page.locator('.ep-footer__language ion-button[size="small"]:visible');
    await expect(languages).toHaveText(['English', 'Español']);
    const boxes = await languages.evaluateAll((elements) =>
      elements.map((element) => {
        const rect = element.getBoundingClientRect();
        return { language: element.getAttribute('lang'), width: rect.width, height: rect.height };
      }),
    );
    for (const box of boxes) {
      expect.soft(box.width, `${box.language} width at ${viewport.width}px`).toBeGreaterThanOrEqual(44);
      expect.soft(box.height, `${box.language} height at ${viewport.width}px`).toBeGreaterThanOrEqual(44);
    }
  });
}
