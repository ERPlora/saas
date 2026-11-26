// The panel's buttons keep their icon where it was when ui gave the icon of a button its gap back
// (saas#54). The panel already set its own gap, on one side only
// (`hubs/frontend/components/buttons.css`, `InvoiceFilters.vue`: `margin-inline-end`), so a ui rule that brought
// back ALL of Ionic's slotted margin (`margin: revert-layer`) also brought its `-0.3em` on the outer side: the icon
// sank 4.5–5.3 px into the button's padding («Pay the invoice», «Download Excel», «Filters»).
// Measured on `/dashboard/billing/invoices` and on the page of an unpaid invoice (rows of billing_seed.py) at 390×844,
// 834×1112 and 1440×900: the icon's outer margin is `0px` and the icon sits as far from the button's left padding as
// the label ends from its right one, as on main.
// flow: ui:ConfirmDialog
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator, Page } from '@playwright/test';

import { panelAccount, qaAccount } from './accounts';
import { expect, seededAndSignedInWarm, test } from './fixtures';
import { settled, VIEWPORTS } from './screen';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SHOTS = join(SAAS_DIR, 'tests', 'e2e', '.artifacts', 'fix-ui-confirmdialog-icon');

const BILLING = qaAccount('BILLING', panelAccount('billing'));

/** The panel's buttons with an icon in `slot="start"` and their own gap rule, by the page they are on («Filters», with
 *  no filter on, is its icon alone). */
const BUTTONS = { list: ['invoices-csv'], invoice: ['pay-invoice'] } as const;

seededAndSignedInWarm('billing_seed.py', BILLING);

interface StartSide {
  /** The icon's margin on the outer side (`margin-inline-start`), as computed. */
  outer: string;
  /** From the button's left padding to the icon, in px. */
  left: number;
  /** From the end of the label (or of the icon, folded) to the button's right padding, in px. */
  right: number;
}

/** Where a button's start icon sits: the button centres its content, so with no outer margin `left` = `right`. */
function startSide(button: Locator): Promise<StartSide> {
  return button.evaluate((el) => {
    const icon = el.querySelector(':scope > [slot="start"]');
    const native = el.shadowRoot?.querySelector('.button-native');
    if (!icon || !native) throw new Error(`no start icon or no native button in ${el.outerHTML}`);
    const box = native.getBoundingClientRect();
    const frame = getComputedStyle(native);
    const innerLeft = box.left + parseFloat(frame.borderLeftWidth) + parseFloat(frame.paddingLeft);
    const innerRight = box.right - parseFloat(frame.borderRightWidth) - parseFloat(frame.paddingRight);
    const iconBox = icon.getBoundingClientRect();
    let end = iconBox.right + parseFloat(getComputedStyle(icon).marginInlineEnd);
    for (const node of el.childNodes) {
      if (node === icon) continue;
      if (node.nodeType === Node.TEXT_NODE && node.textContent?.trim()) {
        const range = document.createRange();
        range.selectNodeContents(node);
        end = Math.max(end, range.getBoundingClientRect().right);
      } else if (node instanceof Element && node.getBoundingClientRect().width > 0) {
        end = Math.max(end, node.getBoundingClientRect().right + parseFloat(getComputedStyle(node).marginInlineEnd));
      }
    }
    return { outer: getComputedStyle(icon).marginInlineStart, left: iconBox.left - innerLeft, right: innerRight - end };
  });
}

/** The page of an invoice Stripe could not charge, with its «Pay the invoice». */
async function unpaidInvoicePath(page: Page): Promise<string> {
  const response = await page.request.get('/api/billing/invoices?status=open&limit=1');
  expect(response.status()).toBe(200);
  const [invoice] = ((await response.json()) as { rows: Array<{ id: string }> }).rows;
  return `/dashboard/billing/invoices/${invoice.id}`;
}

/** Each button on the page on screen keeps its start icon off the edge, at `width`. */
async function expectIconsInPlace(page: Page, testids: readonly string[], width: number): Promise<void> {
  for (const testid of testids) await expect(page.getByTestId(testid).first()).toBeVisible();
  await settled(page);
  for (const testid of testids) {
    const what = `«${testid}» ${width}`;
    const side = await startSide(page.getByTestId(testid).first());
    expect(side.outer, `${what}: ${JSON.stringify(side)}`).toBe('0px');
    expect(Math.abs(side.left - side.right), `${what}: ${JSON.stringify(side)}`).toBeLessThanOrEqual(0.75);
  }
}

test('ui:ConfirmDialog — the panel’s buttons keep their icon off the button’s edge, as on main', async ({ page }) => {
  const invoice = await unpaidInvoicePath(page);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/dashboard/billing/invoices');
    await expectIconsInPlace(page, BUTTONS.list, viewport.width);
    await page.screenshot({ path: join(SHOTS, `FIX-UI-CONFIRMDIALOG-ICON-GAP-saas-${viewport.width}.png`) });
    await page.goto(invoice);
    await expectIconsInPlace(page, BUTTONS.invoice, viewport.width);
  }
});
