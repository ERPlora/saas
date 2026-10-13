// The SaaS's typeface: IBM Plex, as the template pages had it (`templates/partials/erplora_fonts.html`),
// from the same files vendored under static/ (the CSP admits no CDN). Vite bundles the woff2 files
// the @font-face rules name. The Hub ships no web font (packages/ui variables.css, hub#1166): the
// SaaS sets Ionic's font family itself, and only next to the @font-face that serves it.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const FONTS_CSS = readFileSync(join(HERE, 'fonts.css'), 'utf8');

function importedSheets(css: string, from: string): string[] {
  return [...css.matchAll(/@import\s+['"]([^'"]+)['"]/g)].map((m) => resolve(from, m[1]));
}

describe('frontend/fonts.css', () => {
  const [plex] = importedSheets(FONTS_CSS, HERE);
  const plexCss = plex ? readFileSync(plex, 'utf8') : '';

  it("imports the template pages' font sheet from static/", () => {
    expect(plex).toBe(resolve(HERE, '..', 'static', 'css', 'erplora-fonts.css'));
  });

  it('serves every font file that sheet names (vendored, same origin)', () => {
    const files = [...plexCss.matchAll(/url\("([^"]+)"\)/g)].map((m) => resolve(dirname(plex), m[1]));
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) expect(existsSync(file), file).toBe(true);
    expect(plexCss).toMatch(/--font-body:\s*"IBM Plex Sans"/);
    expect(plexCss).toMatch(/--font-mono:\s*"IBM Plex Mono"/);
  });

  it("makes IBM Plex Sans Ionic's font family, as the template's ionic-theme.css did", () => {
    expect(FONTS_CSS).toMatch(/:root\s*{\s*--ion-font-family:\s*var\(--font-body\);\s*}/);
  });
});
