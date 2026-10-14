// The invoices' toolbar on ONE line from 641 px (audit 2026-10-14, R-14: «Download Excel» alone on a second
// line at 834, 1024 and 1180 px). DataTable lays its bar out as one flex row that wraps item by item, and the
// room left depends on the side menu, the language and what the bar holds, not on the viewport: so what fits is
// measured on the row's own box (a ResizeObserver), as DataTable fits its columns (W-19).
//   - When the watched item falls below the first line, the toolbar folds (`compact`: the page folds the item
//     to its icon and narrows the search).
//   - Folded, it tries the full toolbar again only when the row grows wider than when it folded — never back
//     and forth at one width — or when asked (`retry`: what sits in the toolbar changed).
import { nextTick, readonly, type Ref, shallowRef, watch } from 'vue';

/** Whether `item` sits below the first visible item of its wrapping flex row (a hidden one has no height). */
export function wrapped(item: Element): boolean {
  const row = item.parentElement;
  if (!row) return false;
  const first = [...row.children].find((child) => child !== item && child.getBoundingClientRect().height > 0);
  if (!first) return false;
  return item.getBoundingClientRect().top >= first.getBoundingClientRect().bottom;
}

export function useToolbarFit(item: Readonly<Ref<Element | null | undefined>>) {
  const compact = shallowRef(false);
  /** The row's width when it folded: it unfolds only wider than that. */
  let foldedAt = 0;

  function measure(): void {
    const element = item.value;
    const row = element?.parentElement;
    if (!element || !row) return;
    const width = row.clientWidth;
    if (!compact.value) {
      if (wrapped(element)) {
        compact.value = true;
        foldedAt = width;
      }
    } else if (width > foldedAt) {
      void unfold();
    }
  }

  /** Paints the full toolbar and measures it again: it folds back if it still wraps. */
  async function unfold(): Promise<void> {
    compact.value = false;
    await nextTick();
    measure();
  }

  // The row is DataTable's (the item's parent); it is replaced when the bar is (an empty list hides it).
  watch(
    item,
    (element, _before, onCleanup) => {
      const row = element?.parentElement;
      if (!row || typeof ResizeObserver === 'undefined') return;
      const observer = new ResizeObserver(() => measure());
      observer.observe(row);
      onCleanup(() => observer.disconnect());
    },
    { immediate: true, flush: 'post' },
  );

  /** Tries the full toolbar again: what sits in it changed. */
  function retry(): void {
    if (compact.value) void unfold();
  }

  return { compact: readonly(compact), retry };
}
