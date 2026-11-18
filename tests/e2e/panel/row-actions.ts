// A row action of a `DataTable` (`@erplora/ui`) is one of the row's buttons (two at most) or an entry of its «⋮», and
// the table decides which by measuring its box a frame or more after a resize or new rows: what the row showed a
// moment ago may not be what a click finds.
import type { Locator, Page } from '@playwright/test';

/** The page on screen: Ionic keeps the ones left behind in the DOM, hidden. */
const shown = (page: Page): Locator => page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last();

/** The row menu «⋮», which Ionic presents outside the page. */
export const rowMenu = (page: Page): Locator => page.locator('ion-popover.data-table__row-menu');

/** The hooks `DataTable` gives a row action of `table`: its button (and its entry inside «⋮»), and the row's «⋮». */
function rowHooks(table: string, id: string, action: string): { hook: string; menuHook: string } {
  return { hook: `${table}-row-${id}-${action}`, menuHook: `${table}-row-${id}-menu` };
}

/** Runs a row action: its button, or its entry inside «⋮» when the row keeps it there. The click goes to whichever of
 *  the two the row shows when it lands, and the entry is looked for in «⋮» only when that is where it landed. */
export async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const { hook, menuHook } = rowHooks(table, id, action);
  const landed = await clickLanding(page, shown(page).getByTestId(hook).or(shown(page).getByTestId(menuHook)).first());
  if (landed === hook) return;
  if (landed !== menuHook) throw new Error(`rowAction ${hook}: the click landed on ${landed ?? 'nothing'}, neither the button nor «⋮»`);
  await rowMenu(page).getByTestId(hook).click();
}

/** Clicks `target` and says the `data-testid` of what the click landed on. A locator that matches either of two things
 *  (`a.or(b)`) is resolved again on each try, so the answer is what was there when the click went through. */
async function clickLanding(page: Page, target: Locator): Promise<string | null> {
  type Landing = Window & { e2eClickLanding?: string | null };
  await page.evaluate(() => {
    const record = (event: Event) => {
      (window as Landing).e2eClickLanding = (event.target as Element | null)?.closest('[data-testid]')?.getAttribute('data-testid') ?? null;
    };
    (window as Landing).e2eClickLanding = undefined;
    document.addEventListener('click', record, { capture: true, once: true });
  });
  await target.click();
  return page.evaluate(() => (window as Landing).e2eClickLanding ?? null);
}
