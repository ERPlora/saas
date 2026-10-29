// The one «no horizontal scroll» measure of the e2e, for the public project and the panel's alike (the Hub's twin is
// `horizontalOverflow` of its tests/e2e/helpers.ts). `horizontal-overflow.test.ts` keeps every spec on it.
import type { Page } from '@playwright/test';

/**
 * How many pixels of the page lie past the right edge of their box, 0 when everything fits its width: the document's
 * and, in every `ion-content` (the panel page's, the pinned side menu's, an open sheet's), its scroll box, in its shadow
 * root (`part="scroll"`; a hidden one is 0 wide). Ionic pins the `body` to the window, so a panel screen that runs past
 * the right edge is cut inside its `ion-content` and the document never grows: the document alone read 0 with a 1600 px
 * block on a page at 390. A page without Ionic (the public web, a template) scrolls its document, read here too.
 */
export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const boxes: Element[] = [document.documentElement];
    for (const content of document.querySelectorAll('ion-content')) {
      const scroll = content.shadowRoot?.querySelector('[part~="scroll"]');
      if (scroll) boxes.push(scroll);
    }
    return Math.max(0, ...boxes.map((box) => box.scrollWidth - box.clientWidth));
  });
}
