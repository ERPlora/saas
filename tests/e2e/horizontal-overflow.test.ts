// flow: e2e-overflow — FIX of the e2e harness (FIX-HUB-E2E-HORIZONTAL-SCROLL-CHECK-BLIND-TO-ION-CONTENT; the Hub's twin is
// its tests/e2e/horizontal-overflow.test.ts)
// Every «no horizontal scroll» check of the e2e goes through `horizontalOverflow(page)` (horizontal-overflow.ts), which
// reads the document and every `ion-content` on screen. A spec that measures the document by hand (`documentElement.
// scrollWidth` against the window) is blind to a panel screen cut inside `ion-content`: Ionic pins the `body`, so the
// document never grows. No ratchet: no file of the e2e but horizontal-overflow.ts measures it.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The file of the one measure. */
const MEASURE = 'horizontal-overflow.ts';

/** The ways of reading how wide the document is: its root's, its scrolling element's or its body's `scrollWidth`. */
const DOCUMENT_WIDTH = /\b(?:documentElement|scrollingElement|document\s*\.\s*body)\s*!?\s*\??\.\s*scrollWidth\b/g;

/** `file:line` of each line of `source` (the file `name`) that reads how wide the document is. */
function documentMeasures(name: string, source: string): string[] {
  return source.split('\n').flatMap((line, index) => (line.match(DOCUMENT_WIDTH) ? [`${name}:${index + 1}`] : []));
}

/** The files of the e2e, `panel/` included (the specs and their helpers, not Vitest's own tests nor the artifacts). */
function e2eFiles(): string[] {
  return (readdirSync(E2E_DIR, { recursive: true }) as string[])
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts') && !name.startsWith('.') && !name.includes('node_modules'))
    .sort();
}

describe('the e2e checks for a horizontal scroll go through horizontalOverflow() of horizontal-overflow.ts', () => {
  it('no file of tests/e2e but horizontal-overflow.ts measures the document by hand: the check is horizontalOverflow(page)', () => {
    const found = e2eFiles()
      .filter((name) => name !== MEASURE)
      .flatMap((name) => documentMeasures(name, readFileSync(join(E2E_DIR, name), 'utf8')));
    expect(found).toEqual([]);
  });

  it('the scan sees the panel’s specs as well as the public ones', () => {
    expect(e2eFiles()).toEqual(expect.arrayContaining(['public-web.spec.ts', join('panel', 'login.spec.ts')]));
  });

  it('horizontal-overflow.ts has the one measure, and it reads the document and the scroll box of every ion-content', () => {
    const source = readFileSync(join(E2E_DIR, MEASURE), 'utf8');
    expect(source).toContain('export async function horizontalOverflow(page: Page): Promise<number>');
    expect(source).toContain('const boxes: Element[] = [document.documentElement];');
    expect(source).toContain("for (const content of document.querySelectorAll('ion-content'))");
    expect(source).toContain(`content.shadowRoot?.querySelector('[part~="scroll"]')`);
  });

  it('the count reads every way of measuring the document by hand, and the helper or an element’s own width as none', () => {
    const lines = [
      'page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)',
      'page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)',
      'return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);',
      'return document.scrollingElement!.scrollWidth - innerWidth;',
      'return document.body.scrollWidth > innerWidth;',
    ];
    expect(lines.map((line) => documentMeasures('x.ts', line))).toEqual(lines.map(() => ['x.ts:1']));
    expect(documentMeasures('x.ts', 'expect.poll(() => horizontalOverflow(page)).toBeLessThanOrEqual(0);')).toEqual([]);
    expect(documentMeasures('x.ts', 'if (table.scrollWidth > table.clientWidth + 1) found.push(table);')).toEqual([]);
  });
});
