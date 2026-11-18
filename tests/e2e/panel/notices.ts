// The shell's action center as the panel's specs read it: the bell of the topbar, its panel and the notice it
// features. Ionic keeps the pages it left in the DOM, hidden, each with its own topbar: only the one on screen counts.
import type { Locator, Page } from '@playwright/test';

import { expect } from './fixtures';

/** What the bell follows on every page, in the page's own stream: the open invoices and the businesses they belong to. */
export const BELL_SUBSCRIPTIONS = ['billing.invoice.list {"limit":100,"status":"open"}', 'hubs.business.list {"limit":100}'] as const;

/** The bell of the page on screen. */
export function bell(page: Page): Locator {
  return page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last().getByTestId('action-bell');
}

/** The bell with `count` things pending: the red pill with its number, or the bare bell for `0`. */
export async function expectBell(page: Page, count: number): Promise<void> {
  if (count === 0) {
    await expect(bell(page)).not.toHaveClass(/has-notices/);
    return;
  }
  await expect(bell(page)).toHaveClass(/has-notices/);
  await expect(bell(page)).toHaveAttribute('data-severity', 'danger');
  await expect(bell(page).locator('.action-bell__count')).toHaveText(String(count));
}

/** Opens the bell's panel, unless it is open already. */
export async function openNotices(page: Page): Promise<Locator> {
  const panel = page.getByTestId('action-panel');
  if (!(await panel.isVisible())) await bell(page).click();
  await expect(panel).toBeVisible();
  return panel;
}

/** The panel open with the notice whose title names `name` on top (a row brings it there); gives that notice. */
export async function featureNotice(page: Page, name: string): Promise<Locator> {
  const panel = await openNotices(page);
  const featured = panel.getByTestId('action-featured');
  await expect(featured).toBeVisible();
  if (!(await featured.locator('h3').innerText()).includes(name)) {
    await panel.getByTestId('action-row').filter({ hasText: name }).click();
  }
  await expect(featured.locator('h3')).toContainText(name);
  return featured;
}

/** The two buttons of a featured notice. */
export const primary = (featured: Locator): Locator => featured.locator('.action-featured__primary');
export const secondary = (featured: Locator): Locator => featured.locator('.action-featured__secondary');
