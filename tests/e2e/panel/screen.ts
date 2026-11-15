import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, type Locator, type Page } from '@playwright/test';

import { overflowingBoxes } from '../horizontal-overflow';
import { SAAS_DIR } from './django';

const HERE = dirname(fileURLToPath(import.meta.url));
const ARTIFACTS = join(HERE, '..', '.artifacts', 'panel');

/** Phone, tablet and desktop. */
export const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
  { width: 1440, height: 900 },
] as const;

/**
 * What scrolls sideways on the page on screen: Ionic pins `body` (its width never grows), so the
 * scroll is read where it happens — the scroll box of every `ion-content` and the document (a page
 * that is no Ionic page, Django's admin or a template, scrolls its document), by the one
 * measure (`overflowingBoxes` of ../horizontal-overflow.ts, past 1 px), and every DataTable's own
 * scroll box of the page, which also says so with `data-table__scroll--overflow`.
 */
export async function sidewaysScroll(page: Page): Promise<string[]> {
  const boxes = await overflowingBoxes(page, 1);
  const tables = await page.evaluate(() => {
    const shown = [...document.querySelectorAll('ion-router-outlet > .ion-page:not(.ion-page-hidden)')].at(-1) ?? document;
    const found: string[] = [];
    for (const table of shown.querySelectorAll<HTMLElement>('.data-table__scroll')) {
      if (table.scrollWidth > table.clientWidth + 1) found.push(`data-table ${table.scrollWidth} > ${table.clientWidth}`);
      if (table.classList.contains('data-table__scroll--overflow')) found.push('data-table__scroll--overflow');
    }
    return found;
  });
  return [...boxes, ...tables];
}

/**
 * Nothing scrolls sideways (`sidewaysScroll`) once the page has re-laid out, `label` naming the failure. Right after a
 * resize, or the assistant docking beside the page, a DataTable fits its new box over a few frames (folds its row
 * actions, then hands over to cards): one measure taken at once can catch the list half-way, still as wide as before,
 * and report a scroll nobody sees (saas#319). On the real Hub of a cross spec, its side menu (`ion-split-pane`) stays
 * pinned for a frame after the window shrinks below `lg`, its page 150 px wide (saas#380). So it is measured until it
 * has settled.
 */
export async function expectNoSidewaysScroll(page: Page, label: string): Promise<void> {
  await expect.poll(() => sidewaysScroll(page), { message: label }).toEqual([]);
}

/** How long `settled` waits for the page to stop moving: Ionic's overlays enter in well under a second. */
const SETTLE_TIMEOUT_MS = 10_000;

/**
 * What moves on the page now (run in the page, so self-contained): every finite animation running in the document
 * and in every open shadow root under it, however deep. `document.getAnimations()` leaves shadow roots out, and
 * Ionic animates its overlays (`ion-toast`, `ion-modal`, `ion-popover`) inside theirs. Endless ones (spinners)
 * never stop, so they never count.
 */
function movingInPage(): string[] {
  const roots: Array<Document | ShadowRoot> = [document];
  const moving: string[] = [];
  for (const root of roots) {
    for (const element of root.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
    for (const animation of root.getAnimations()) {
      if (animation.playState !== 'running' || animation.effect?.getTiming().iterations === Infinity) continue;
      const target = (animation.effect as KeyframeEffect | null)?.target;
      moving.push(`${root instanceof ShadowRoot ? `${root.host.localName} › ` : ''}${target?.localName ?? '?'}`);
    }
  }
  return moving;
}

/** A page that navigates while `settled` asks what moves: it asks the new page next (as `waitForFunction` did). */
function navigating(error: Error): string[] {
  if (!/Execution context was destroyed/.test(error.message)) throw error;
  return ['(navigating)'];
}

/**
 * Settled: the fonts loaded, nothing moving (an overlay of Ionic entering included; endless spinners aside) and the
 * page painted as it is now. The last one is what a screenshot right after `setViewportSize` needs: taken before the
 * browser paints a frame at the new size, it repeats the top of the page at its bottom (`repeatedTop`). A page that
 * still moves after `SETTLE_TIMEOUT_MS` fails the spec, naming what moves.
 */
export async function settled(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await expect
    .poll(() => page.evaluate(movingInPage).catch(navigating), { message: 'settled(): still moving', timeout: SETTLE_TIMEOUT_MS, intervals: [16] })
    .toEqual([]);
  // A frame's callbacks run before it is painted; the next frame's, once it has been.
  await page.evaluate(() => new Promise<void>((painted) => requestAnimationFrame(() => requestAnimationFrame(() => painted()))));
}

/** The panel's side menu: pinned from `lg` (992 px), its drawer behind the topbar's menu button below. Opens the drawer
 *  when the menu is not on screen, and waits until it has slid in with its entries inside the screen. */
export async function openMenu(page: Page): Promise<void> {
  const entries = page.locator('ion-menu .nav-item');
  await expect(entries.first()).toBeAttached();
  await settled(page);
  if (!(await entries.first().isVisible())) {
    await page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-menu-button').last().click();
    await expect(entries.first()).toBeVisible();
    // The drawer slides in: it counts as open once its animation ends and its entries sit inside the screen.
    await expect
      .poll(() => page.evaluate(() => (document.querySelector('ion-menu') as (HTMLElement & { isOpen: () => Promise<boolean> }) | null)?.isOpen() ?? false))
      .toBe(true);
    await expect.poll(async () => (await entries.first().boundingBox())?.x ?? -1).toBeGreaterThanOrEqual(0);
  }
}

/** Closes the drawer `openMenu` opened (nothing to do where the menu is pinned). */
export async function closeMenu(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const menu = document.querySelector('ion-menu') as (HTMLElement & { close?: () => Promise<boolean> }) | null;
    await menu?.close?.();
  });
}

/** The fewest rows `repeatedTop` counts as a stripe. */
const STRIPE_MIN_ROWS = 8;

/**
 * How many rows at the bottom of `png`, a screenshot of `page`, repeat the first rows of the image: 0 when
 * none. It is what a capture taken before the browser painted the page at its new size shows (the area the
 * resize uncovered, filled with the top of the page): evidence of a screen nobody saw. A stripe of one flat
 * colour (a background at both ends) does not count. Decoded in `page`'s browser: the e2e has no image library.
 */
export async function repeatedTop(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(
    async ({ base64, minRows }) => {
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const { width, height } = bitmap;
      const context = new OffscreenCanvas(width, height).getContext('2d');
      if (!context) throw new Error('repeatedTop: no 2d context to read the screenshot');
      context.drawImage(bitmap, 0, 0);
      const pixels = new Uint32Array(context.getImageData(0, 0, width, height).data.buffer);
      const sameRow = (a: number, b: number) => {
        for (let x = 0; x < width; x++) if (pixels[a * width + x] !== pixels[b * width + x]) return false;
        return true;
      };
      const flatRow = (row: number) => {
        for (let x = 1; x < width; x++) if (pixels[row * width + x] !== pixels[row * width]) return false;
        return true;
      };
      for (let rows = Math.floor(height / 2); rows >= minRows; rows--) {
        let repeated = true;
        let flat = true;
        for (let row = 0; row < rows && repeated; row++) {
          repeated = sameRow(height - rows + row, row);
          flat &&= flatRow(row);
        }
        if (repeated && !flat) return rows;
      }
      return 0;
    },
    { base64: png.toString('base64'), minRows: STRIPE_MIN_ROWS },
  );
}

/** Path of a screenshot under `tests/e2e/.artifacts/panel/` (ignored by git). */
export function shot(name: string): string {
  mkdirSync(ARTIFACTS, { recursive: true });
  return join(ARTIFACTS, `${name}.png`);
}

/** One of `VIEWPORTS`. */
export type Viewport = (typeof VIEWPORTS)[number];

/** What a spec's walk through `VIEWPORTS` (`captureAtEverySize`) adds at each size. */
export interface EverySizeOptions {
  /** The whole page captured (the default), or what the window shows. */
  fullPage?: boolean;
  /** What is captured instead of the page: a card whose page scrolls inside its content. */
  of?: Locator;
  /** What follows the width in the capture's name, `<prefix>-<key>-<width>-<suffix>`: the language of the run. */
  suffix?: string;
  /** The spec's own checks once nothing scrolls sideways, before the capture. */
  checks?: (size: Viewport) => Promise<void>;
  /** What undoes `ready` once the capture is taken, before the next size: the menu it opened, closed. */
  after?: () => Promise<void>;
}

/**
 * A spec's walk through `VIEWPORTS` (`captureAtEverySize`): `ready` at each size, then the capture. `options` may be
 * `fullPage` alone, as the billing specs pass it (`false`: what the window shows).
 */
export type AtEverySize = (
  page: Page,
  key: string,
  ready: (size: Viewport) => Promise<void>,
  options?: boolean | EverySizeOptions,
) => Promise<void>;

/**
 * The walk through `VIEWPORTS` of the specs whose captures start with `prefix`: at each size, `ready`; once the page
 * has settled nothing scrolls sideways (`<key> at <width>`), the spec's `checks` pass, and a capture
 * `<prefix>-<key>-<width>` (or `…-<width>-<suffix>`) is taken, of the whole page or of `of`; then `after`. It ends
 * back at the desktop size.
 */
export function captureAtEverySize(prefix: string): AtEverySize {
  return async (page, key, ready, options = {}) => {
    const { fullPage = true, of, suffix, checks, after }: EverySizeOptions =
      typeof options === 'boolean' ? { fullPage: options } : options;
    for (const size of VIEWPORTS) {
      await page.setViewportSize(size);
      await ready(size);
      await settled(page);
      expect(await sidewaysScroll(page), `${key} at ${size.width}`).toEqual([]);
      await checks?.(size);
      const path = shot(suffix === undefined ? `${prefix}-${key}-${size.width}` : `${prefix}-${key}-${size.width}-${suffix}`);
      await (of ? of.screenshot({ path }) : page.screenshot({ path, fullPage }));
      await after?.();
    }
    await page.setViewportSize(VIEWPORTS[VIEWPORTS.length - 1]);
  };
}

/**
 * A dialog that slides in again at a new size (below 640px it is a sheet from the bottom) is in place once its
 * button `testid` is whole on screen and stays put for a frame: the slide runs in Ionic's shadow DOM, where
 * `settled` does not see it, and a capture taken before shows the sheet halfway.
 */
export async function dialogInPlace(page: Page, testid: string): Promise<void> {
  const button = page.getByTestId(testid);
  await expect(button).toBeInViewport({ ratio: 1 });
  await button.evaluate(
    (element) =>
      new Promise<void>((still) => {
        let last = '';
        const frame = () => {
          const { top, left, width, height } = element.getBoundingClientRect();
          const now = `${top},${left},${width},${height}`;
          if (now === last) still();
          else {
            last = now;
            requestAnimationFrame(frame);
          }
        };
        requestAnimationFrame(frame);
      }),
  );
}

/**
 * The text of `key` (`hubs.domain.title`) in the panel catalogue of `app` (`<app>/frontend/locale/<language>.json`), its
 * `{placeholders}` filled; of a plural (`one | other`), the form for `count`. A spec reads a screen's words from there.
 */
export function catalogueText(app: string, language: 'en' | 'es', key: string, params: Record<string, string | number> = {}): string {
  const catalogue = JSON.parse(readFileSync(join(SAAS_DIR, app, 'frontend', 'locale', `${language}.json`), 'utf8')) as unknown;
  const text = key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalogue);
  if (typeof text !== 'string') throw new Error(`no text ${key} in ${app}/frontend/locale/${language}.json`);
  const forms = text.split(' | ');
  const form = forms.length > 1 && params.count !== 1 ? forms[1] : forms[0];
  return form.replace(/\{(\w+)\}/g, (_, name: string) => String(params[name] ?? `{${name}}`));
}

/**
 * The toasts that say `text`, the newest last: `shell/toast.ts` closes the one on screen as it presents the next, so
 * for a moment both are in the page, the new one still hidden. `.last()` is the one just shown; `toHaveCount(0)`, that
 * none is left (never `getByText`, which strict mode refuses while there are two).
 */
export function toast(page: Page, text: string | RegExp): Locator {
  return page.locator('ion-toast').filter({ hasText: text });
}
