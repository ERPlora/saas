// The panel's buttons keep their icon where it was when ui gave the icon of a button its gap back
// (FIX-UI-CONFIRMDIALOG-ICON-GAP, saas#54). The panel already set its own gap, on one side only
// (`hubs/frontend/components/buttons.css`, `InvoiceFilters.vue`: `margin-inline-end`), so a ui rule that brought
// back ALL of Ionic's slotted margin (`margin: revert-layer`) also brought its `-0.3em` on the outer side: the icon
// sank 4.5–5.3 px into the button's padding («Change card», «Pay the invoice», «Download Excel», «Filters»).
// Measured in the page on `/billing/invoices` (rows of billing_seed.py) at 390×844, 834×1112 and 1440×900: the
// icon's outer margin is `0px` and the icon sits as far from the button's left padding as the label ends from
// its right one, as on main.
// flow: ui:ConfirmDialog
import { execFileSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { expect, panelAccount, qaAccount, settled, signIn, test, VIEWPORTS } from './fixtures';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SHOTS = join(SAAS_DIR, 'tests', 'e2e', '.artifacts', 'fix-ui-confirmdialog-icon');

const BILLING = qaAccount('BILLING', panelAccount('billing'));

/** The panel's buttons on `/billing/invoices` with an icon in `slot="start"` and their own gap rule. */
const BUTTONS = ['unpaid-group-change-card', 'pay-invoice', 'invoices-csv', 'invoices-filters'] as const;

function seedBilling(action: 'seed' | 'clear'): void {
  execFileSync('uv', ['run', 'python', 'tests/e2e/panel/billing_seed.py', action], {
    cwd: SAAS_DIR,
    env: djangoEnv(true),
    stdio: 'pipe',
  });
}

test.beforeEach(async ({ page }) => {
  seedBilling('seed');
  await signIn(page.request, BILLING);
});
test.afterAll(() => seedBilling('clear'));

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

test('ui:ConfirmDialog — the panel’s buttons keep their icon off the button’s edge, as on main', async ({ page }) => {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/billing/invoices');
    for (const testid of BUTTONS) await expect(page.getByTestId(testid).first()).toBeVisible();
    await settled(page);
    for (const testid of BUTTONS) {
      const what = `«${testid}» ${viewport.width}`;
      const side = await startSide(page.getByTestId(testid).first());
      expect(side.outer, `${what}: ${JSON.stringify(side)}`).toBe('0px');
      expect(Math.abs(side.left - side.right), `${what}: ${JSON.stringify(side)}`).toBeLessThanOrEqual(0.75);
    }
    await page.screenshot({ path: join(SHOTS, `FIX-UI-CONFIRMDIALOG-ICON-GAP-saas-${viewport.width}.png`) });
  }
});
