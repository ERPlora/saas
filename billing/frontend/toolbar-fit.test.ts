// The invoices' toolbar on ONE line from 641 px (audit 2026-10-14, R-14: «Download Excel» alone on a second
// line at 834, 1024 and 1180 px). DataTable lays its bar out as one flex row that wraps item by item; what fits
// is measured on that row's own box (as DataTable fits its columns, W-19), never on the viewport: when the
// watched item falls below the first line the toolbar folds; folded, it tries the full one again only when the
// row grows wider than when it folded (no back and forth), or when asked (what sits in it changed).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { effectScope, nextTick, shallowRef } from 'vue';

import { mockResizeObserver } from '../../packages/ui/src/components/DataTable/__tests__/harness';
import { useToolbarFit, wrapped } from './toolbar-fit';

/** A fake layout: each element's box by hand (happy-dom lays nothing out). */
const boxes = new Map<Element, { top: number; height: number }>();
const widths = new Map<Element, number>();

beforeEach(() => {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const box = boxes.get(this) ?? { top: 0, height: 0 };
    return { top: box.top, bottom: box.top + box.height, height: box.height, left: 0, right: 0, width: 0, x: 0, y: box.top, toJSON: () => ({}) } as DOMRect;
  });
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return widths.get(this) ?? 0;
  });
});

afterEach(() => {
  boxes.clear();
  widths.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

/** A toolbar row: a heading hidden on a phone, the search, and the watched button. */
function toolbar() {
  const row = document.createElement('div');
  const hidden = document.createElement('div');
  const search = document.createElement('div');
  const item = document.createElement('button');
  row.append(hidden, search, item);
  document.body.append(row);
  boxes.set(search, { top: 0, height: 36 });
  /** Where the item sits: on the first line, or on the second. */
  const place = (line: 1 | 2) => boxes.set(item, { top: line === 1 ? 2 : 44, height: 32 });
  place(1);
  return { row, item, place };
}

describe('wrapped', () => {
  it('is whether the item sits below the first visible item of its row (a hidden heading does not count)', () => {
    const t = toolbar();
    expect(wrapped(t.item)).toBe(false);
    t.place(2);
    expect(wrapped(t.item)).toBe(true);
  });

  it('alone, or out of a row, it is not wrapped', () => {
    const lone = document.createElement('button');
    expect(wrapped(lone)).toBe(false);
    const row = document.createElement('div');
    row.append(lone);
    boxes.set(lone, { top: 44, height: 32 });
    expect(wrapped(lone)).toBe(false);
  });
});

describe('useToolbarFit', () => {
  function setup() {
    const observers = mockResizeObserver();
    const t = toolbar();
    widths.set(t.row, 800);
    const target = shallowRef<Element | null>(null);
    const scope = effectScope();
    const fit = scope.run(() => useToolbarFit(target))!;
    /** The row's box changed (a window resize, a side menu…): the observer reports it. */
    const resize = async (width: number) => {
      widths.set(t.row, width);
      observers.fire();
      await nextTick();
      await nextTick();
    };
    return { ...t, target, fit, observers, resize, scope };
  }

  it('full while everything fits on one line', async () => {
    const s = setup();
    s.target.value = s.item;
    await nextTick();
    await s.resize(800);
    expect(s.fit.compact.value).toBe(false);
  });

  it('folds when the item falls to a second line, and stays folded at that width once it fits', async () => {
    const s = setup();
    s.target.value = s.item;
    await nextTick();
    s.place(2);
    await s.resize(760);
    expect(s.fit.compact.value).toBe(true);
    s.place(1);
    await s.resize(760);
    expect(s.fit.compact.value).toBe(true);
  });

  it('tries the full toolbar again when the row grows wider, and folds again if it still does not fit', async () => {
    const s = setup();
    s.target.value = s.item;
    await nextTick();
    s.place(2);
    await s.resize(760);
    // Wider, but the full toolbar still wraps: folded again, now at this width.
    await s.resize(780);
    expect(s.fit.compact.value).toBe(true);
    // Wider still and it fits: full.
    s.place(1);
    await s.resize(1100);
    expect(s.fit.compact.value).toBe(false);
  });

  it('`retry` tries the full toolbar again (what sits in it changed)', async () => {
    const s = setup();
    s.target.value = s.item;
    await nextTick();
    s.place(2);
    await s.resize(760);
    expect(s.fit.compact.value).toBe(true);
    s.place(1);
    s.fit.retry();
    await nextTick();
    await nextTick();
    expect(s.fit.compact.value).toBe(false);
  });

  it('stops watching when its scope ends', async () => {
    const s = setup();
    s.target.value = s.item;
    await nextTick();
    s.scope.stop();
    s.place(2);
    await s.resize(700);
    expect(s.fit.compact.value).toBe(false);
  });
});
