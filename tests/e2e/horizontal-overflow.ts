// The one «no horizontal scroll» measure of the e2e, for the public project and the panel's alike (the Hub's twin is
// `horizontalOverflow` of its tests/e2e/helpers.ts). `horizontal-overflow.test.ts` keeps every spec on it.
import type { Page } from '@playwright/test';

/** A box the measure reads: which one, how wide its content is and how wide the box is. */
interface BoxWidth {
  box: 'document' | 'ion-content';
  scrollWidth: number;
  clientWidth: number;
}

/**
 * The boxes the measure reads (run in the page, so self-contained): the document's and, in every `ion-content` (the
 * panel page's, the pinned side menu's, an open sheet's), its scroll box, in its shadow root (`part="scroll"`; a hidden
 * one is 0 wide).
 */
function boxWidths(): BoxWidth[] {
  const boxes: Array<[BoxWidth['box'], Element]> = [['document', document.documentElement]];
  for (const content of document.querySelectorAll('ion-content')) {
    const scroll = content.shadowRoot?.querySelector('[part~="scroll"]');
    if (scroll) boxes.push(['ion-content', scroll]);
  }
  return boxes.map(([box, element]) => ({ box, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }));
}

/**
 * How many pixels of the page lie past the right edge of their box, 0 when everything fits its width, in any box of
 * `boxWidths`. Ionic pins the `body` to the window, so a panel screen that runs past the right edge is cut inside its
 * `ion-content` and the document never grows: the document alone read 0 with a 1600 px block on a page at 390. A page
 * without Ionic (the public web, a template) scrolls its document, read here too.
 */
export async function horizontalOverflow(page: Page): Promise<number> {
  const boxes = await page.evaluate(boxWidths);
  return Math.max(0, ...boxes.map(({ scrollWidth, clientWidth }) => scrollWidth - clientWidth));
}

/**
 * Each box of `boxWidths` whose content runs more than `slack` px past its right edge, named for a message as
 * `<box> <scrollWidth> > <clientWidth>` (`document 1600 > 390`, `ion-content 1632 > 390`): what scrolls sideways, by the
 * same measure. `sidewaysScroll` of panel/fixtures.ts reads it with its 1 px of slack.
 */
export async function overflowingBoxes(page: Page, slack = 0): Promise<string[]> {
  const boxes = await page.evaluate(boxWidths);
  return boxes
    .filter(({ scrollWidth, clientWidth }) => scrollWidth > clientWidth + slack)
    .map(({ box, scrollWidth, clientWidth }) => `${box} ${scrollWidth} > ${clientWidth}`);
}
