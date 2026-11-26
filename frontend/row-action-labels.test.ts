// A DataTable row action with an icon is an icon-only button, named by its label (and titled with it); `showLabel`
// also paints the text, which is only for an action whose icon does not say it alone. Any other `showLabel` in the
// panel fails here, and so does an exception that is no longer used: the list only shrinks.
import { describe, expect, it } from 'vitest';

/** `<file>#<action id>` → why its icon cannot stand alone. */
const LABELLED_ROW_ACTIONS: Record<string, string> = {
  'billing/frontend/components/InvoicesTab.vue#pay': 'a card is also the icon of «Payment method» on the same page',
};

const sources = import.meta.glob<string>(['../*/frontend/**/*.{ts,vue}', './**/*.{ts,vue}', '!**/*.test.ts', '!**/__tests__/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

/** Each `showLabel:` of the panel's sources, as `<file>#<id>` with the nearest `id: '…'` before it. */
function labelledRowActions(): string[] {
  return Object.entries(sources).flatMap(([path, source]) => {
    const file = path.replace(/^\.\.\//, '').replace(/^\.\//, 'frontend/');
    return [...source.matchAll(/\bshowLabel\s*:/g)].map((match) => {
      const id = [...source.slice(0, match.index).matchAll(/\bid:\s*'([^']+)'/g)].at(-1)?.[1] ?? '?';
      return `${file}#${id}`;
    });
  });
}

describe('row actions of the panel', () => {
  it('paint their text (`showLabel`) only where the icon does not say it alone', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50);
    expect(labelledRowActions().sort()).toEqual(Object.keys(LABELLED_ROW_ACTIONS).sort());
  });
});
