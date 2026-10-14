// The panel's lists fill their page (Ioan, 2026-10-14): between the topbar and the tabbar, the toolbar
// and the footer stay and the rows scroll inside, at 390, 834 and 1440 px. `panel-fill.css` (loaded by
// main.ts for every page) is the height chain: AppPage `content-layout="detail-fill"` gives the page's
// box its height; a `.panel-fill` stack takes it whole; what sits above and under the list keeps its
// own height and the list (a DataTable with `fill`, or a nested `.panel-fill` that holds one) takes the
// rest. On a phone the list follows DataTable's own `fill` (it grows with its rows from the page's
// height). happy-dom lays nothing out, so this reads the stylesheet; the
// layout itself is measured in Chrome (tests/e2e/panel/viewports.spec.ts).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'panel-fill.css'), 'utf8')
  // Comments out, whitespace folded: rules compare as written.
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/\s+/g, ' ');

/** The `@media (…)` block of the stylesheet with that condition. */
function media(condition: string): string {
  const start = CSS.indexOf(`@media ${condition} {`);
  if (start === -1) return '';
  let depth = 0;
  for (let at = CSS.indexOf('{', start); at < CSS.length; at += 1) {
    if (CSS[at] === '{') depth += 1;
    if (CSS[at] === '}' && --depth === 0) return CSS.slice(CSS.indexOf('{', start) + 1, at);
  }
  return '';
}

/** The declarations of the rule with exactly that selector list in `css` (top level unless a block is given). */
function rule(selector: string, css = CSS.replace(/@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, '')): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s*');
  const found = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  return found ? found[1].trim() : '';
}

const PHONE = '(max-width: 640px)';
const DESK = '(min-width: 641px)';

describe('panel-fill.css: the height chain of a panel page with a list', () => {
  it('a `.panel-fill` stack takes its box whole, as a column', () => {
    expect(rule('.panel-fill')).toBe('display: flex; flex-direction: column; height: 100%; min-height: 0;');
  });

  it('what sits above and under the list keeps its height', () => {
    expect(rule('.panel-fill > *')).toBe('flex: 0 0 auto;');
  });

  it('on a desk or a tablet the list takes the rest, never less than a few rows (notices above push the page)', () => {
    // Stronger than DataTable's scoped `min-height: 0` of `.data-table--fill` (a class and its attribute).
    expect(rule('.panel-fill > .data-table.data-table--fill, .panel-fill > .panel-fill', media(DESK))).toBe(
      'flex: 1 1 0; min-height: var(--panel-list-min, 20rem);',
    );
    // Nothing of it outside the media query: a phone follows DataTable's own `fill`.
    expect(rule('.panel-fill > .data-table.data-table--fill, .panel-fill > .panel-fill')).toBe('');
  });

  it('on a phone the list grows with its rows from the page’s height, as DataTable’s `fill` does there (one scroll)', () => {
    const phone = media(PHONE);
    expect(rule('.panel-fill > .data-table.data-table--fill, .panel-fill > .panel-fill', phone)).toBe('flex: 1 0 auto;');
    // A nested stack is as tall as what it holds (a `height: 100%` basis would add the siblings above it).
    expect(rule('.panel-fill > .panel-fill', phone)).toBe('height: auto;');
    expect(phone).not.toMatch(/data-table__cards|data-table__surface|data-table__scroll/);
  });

  it('on a phone a list with a search drops its heading: the topbar and the tabbar name it, its footer counts it', () => {
    expect(rule('.panel-fill .data-table__bar-main:has(> .data-table__search) > .data-table__title-wrap', media(PHONE))).toBe('display: none;');
    // Never on a desk.
    expect(rule('.panel-fill .data-table__bar-main:has(> .data-table__search) > .data-table__title-wrap')).toBe('');
  });
});
