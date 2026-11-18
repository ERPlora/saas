// The panel's chrome around every page: «Skip to content» hidden until it has the focus, Back without ☰ in a
// detail page (the menu at the top level, Back inside a business) and targets of 44 px on a phone or a touch
// screen (buttons, icon buttons, segments and tabs, the menu button, chips). happy-dom lays nothing out, so
// this reads the stylesheet; the sizes are measured in Chrome (tests/e2e/panel/chrome.spec.ts).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'panel-chrome.css'), 'utf8')
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

/** The declarations of the rule with exactly that selector list in `css`. */
function rule(selector: string, css = CSS): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s*');
  const found = new RegExp(`(?:^|[}{])\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  return found ? found[1].trim() : '';
}

const TOUCH = '(max-width: 640px), (pointer: coarse)';

describe('panel-chrome.css', () => {
  it('«Skip to content» is out of sight until it has the focus, then on top of everything', () => {
    expect(rule('.skip-link')).toContain('transform: translateY(-200%)');
    expect(rule('.skip-link')).toContain('position: fixed');
    expect(rule('.skip-link:focus, .skip-link:focus-visible')).toContain('transform: none');
  });

  it('a detail page (Back in the topbar) has no ☰: Back inside a business, the menu at the top level', () => {
    expect(rule(".app-topbar ion-buttons[slot='start']:has(> [data-testid='topbar-back']) > ion-menu-button")).toBe('display: none;');
  });

  // The shell lays the bar out on a phone: the title's box takes its text and the two groups share the rest alike, so
  // it stays centred beside the bell's pill. Groups sized to their buttons here pushed it 45 px off at 390.
  it('leaves the topbar’s button groups to the shell, which keeps the title centred on a phone', () => {
    expect(CSS).not.toContain('ion-toolbar.ios > ion-buttons');
  });

  it('an outlined button on a table’s grey bar uses the accessible primary text («Download Excel» at 4.19:1)', () => {
    expect(rule('.data-table__bar ion-button.button-outline:not(.ion-color)')).toBe(
      '--color: var(--ep-primary-text, var(--ion-color-primary)); --border-color: var(--ep-primary-text, var(--ion-color-primary));',
    );
  });

  it('on a phone or a touch screen every target is 44 px', () => {
    const touch = media(TOUCH);
    expect(rule('ion-button, ion-buttons ion-button.in-buttons', touch)).toContain('min-height: 44px');
    expect(rule('ion-button.button-has-icon-only, ion-buttons ion-button.in-buttons.button-has-icon-only', touch)).toContain('min-width: 44px');
    expect(rule('ion-menu-button, ion-back-button', touch)).toBe('min-width: 44px; min-height: 44px;');
    expect(rule('ion-segment-button', touch)).toContain('min-height: 44px');
    expect(rule('ion-chip', touch)).toContain('min-height: 44px');
  });
});
