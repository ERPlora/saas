// flow: saas-e2e-settled
// The harness's `settled()` (fixtures.ts), the wait every capture and measurement of the panel's specs takes: once it
// returns, nothing on the screen moves any more. Ionic animates its overlays (`ion-toast`, `ion-modal`, `ion-popover`)
// with Web Animations on elements of their shadow roots, which `document.getAnimations()` leaves out: a capture right
// after it cut the toast at the bottom (FIX-SAAS-BILLING-INVOICE-DOWNLOAD-NETWORK-ERROR-ENGLISH, saas#78). The checks
// here read the page on their own, never through `settled()`'s code.
import type { Page } from '@playwright/test';

import { expect, repeatedTop, settled, shot, test, VIEWPORTS } from './fixtures';

/** The finite animations running in the document and in every open shadow root under it, however deep. */
const stillMoving = (page: Page) =>
  page.evaluate(() => {
    const roots: Array<Document | ShadowRoot> = [document];
    const moving: string[] = [];
    for (const root of roots) {
      for (const element of root.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
      for (const animation of root.getAnimations()) {
        if (animation.playState === 'running' && animation.effect?.getTiming().iterations !== Infinity) {
          const target = (animation.effect as KeyframeEffect | null)?.target;
          moving.push(`${root instanceof ShadowRoot ? `${root.host.localName} › ` : ''}${target?.localName ?? '?'}`);
        }
      }
    }
    return moving;
  });

/** The box of the toast on screen (its `.toast-wrapper`, in its shadow root) and the window's size. */
const toastBox = (page: Page) =>
  page.locator('ion-toast').evaluate((toast) => {
    const box = toast.shadowRoot?.querySelector('.toast-wrapper')?.getBoundingClientRect();
    if (!box) throw new Error('ion-toast without its .toast-wrapper');
    return { top: box.top, bottom: box.bottom, left: box.left, right: box.right, width: innerWidth, height: innerHeight };
  });

test('saas-e2e-settled: after `settled()` a toast of Ionic has stopped, whole on screen, in the three sizes', async ({ signedInPage: page }) => {
  // «Notices from my businesses» with the network down: the shell's error toast, and nothing is saved.
  await page.route(/\/api\/accounts\/preferences$/, (route) =>
    route.request().method() === 'GET' ? route.continue() : route.abort('internetdisconnected'),
  );
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto('/dashboard/account/preferences');
    await expect(page.getByTestId('preferences-hub-alerts')).toBeVisible();
    await settled(page);
    await page.getByTestId('preferences-hub-alerts').click();
    await expect(page.locator('ion-toast')).toBeVisible();
    await settled(page);
    expect(await stillMoving(page), `still moving after settled() at ${viewport.width} px`).toEqual([]);
    const box = await toastBox(page);
    expect(box.top, `toast top at ${viewport.width} px`).toBeGreaterThanOrEqual(0);
    expect(box.left, `toast left at ${viewport.width} px`).toBeGreaterThanOrEqual(0);
    expect(box.bottom, `toast bottom at ${viewport.width} px`).toBeLessThanOrEqual(box.height);
    expect(box.right, `toast right at ${viewport.width} px`).toBeLessThanOrEqual(box.width);
    const png = await page.screenshot({ path: shot(`FIX-SAAS-E2E-SETTLED-IGNORES-IONIC-ANIMATIONS-${viewport.width}`) });
    expect(await repeatedTop(page, png), `rows of the top repeated at the bottom at ${viewport.width} px`).toBe(0);
  }
});

test('saas-e2e-settled: `settled()` waits for an animation two shadow roots deep and not for an endless one', async ({ page }) => {
  await page.goto('/launch');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await settled(page);
  // A host with a shadow root holding an endless animation (a spinner) and, one shadow root further down, a finite one.
  await page.evaluate(() => {
    const host = document.createElement('div');
    const inner = document.createElement('div');
    const spinner = document.createElement('span');
    const deep = document.createElement('span');
    deep.textContent = 'moving';
    host.attachShadow({ mode: 'open' }).append(inner, spinner);
    inner.attachShadow({ mode: 'open' }).append(deep);
    document.body.append(host);
    spinner.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400, iterations: Infinity });
    const finite = deep.animate([{ transform: 'translateX(0)' }, { transform: 'translateX(40px)' }], { duration: 800 });
    (window as unknown as { settledProbe: Animation }).settledProbe = finite;
  });
  await settled(page);
  expect(await page.evaluate(() => (window as unknown as { settledProbe: Animation }).settledProbe.playState)).toBe('finished');
  expect(await stillMoving(page)).toEqual([]);
});

test('saas-e2e-settled: `settled()` keeps waiting when the page reloads under it', async ({ page }) => {
  // Something still moves when the page reloads: `settled()` asks the new page instead of failing with the old one's
  // «Execution context was destroyed». A few rounds, each reloading at another moment of the wait.
  for (let round = 0; round < 5; round++) {
    await page.goto('/launch');
    await expect(page.getByTestId('login-form')).toBeVisible();
    await page.evaluate((delay) => {
      document.body.appendChild(document.createElement('div')).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 1500 });
      setTimeout(() => location.reload(), delay);
    }, 200 + round * 37);
    await settled(page);
  }
  await expect(page.getByTestId('login-form')).toBeVisible();
  expect(await stillMoving(page)).toEqual([]);
});
