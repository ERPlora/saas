// «Skip to content» (audit 2026-10-14, R-11; W-01 of the mockups): the first stop of the keyboard on every page
// of the panel, hidden until it has the focus, that takes it to the page on screen (its `ion-content`) past the
// menu and the topbar. In the page's language, following `<html lang>` as the shell changes it.
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { installSkipLink, SKIP_LINK_ID } from './skip-link';

const TEXTS = { en: 'Skip to content', es: 'Saltar al contenido' };
const NAV = { en: 'Shortcuts', es: 'Atajos' };

function page(hidden: boolean, id: string): string {
  return `<div class="ion-page${hidden ? ' ion-page-hidden' : ''}" id="${id}"><ion-header></ion-header><ion-content></ion-content></div>`;
}

beforeEach(() => {
  document.documentElement.lang = 'en';
  document.body.innerHTML = `<div id="app"><ion-router-outlet id="main">${page(true, 'old')}${page(false, 'shown')}</ion-router-outlet></div>`;
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('installSkipLink', () => {
  it('is the first thing of the page, a link in the page’s language', () => {
    installSkipLink(document, TEXTS, NAV);
    const link = document.body.querySelector('a') as HTMLAnchorElement;
    expect(link.id).toBe(SKIP_LINK_ID);
    expect(link.getAttribute('href')).toBe('#main');
    expect(link.textContent).toBe('Skip to content');
    expect(document.body.firstElementChild?.contains(link)).toBe(true);
  });

  it('lives in a landmark of its own and points at an element that exists (audit 2 S-05: axe `region`)', () => {
    installSkipLink(document, TEXTS, NAV);
    const nav = document.body.firstElementChild as HTMLElement;
    expect(nav.tagName).toBe('NAV');
    expect(nav.getAttribute('aria-label')).toBe('Shortcuts');
    expect(nav.querySelector(`#${SKIP_LINK_ID}`)).not.toBeNull();
    // The shell's outlet (`<ion-router-outlet id="main">`, the menu's `content-id`).
    expect(document.getElementById('main')?.tagName).toBe('ION-ROUTER-OUTLET');
  });

  it('follows the language the shell gives the page', async () => {
    installSkipLink(document, TEXTS, NAV);
    document.documentElement.lang = 'es';
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.getElementById(SKIP_LINK_ID)?.textContent).toBe('Saltar al contenido');
    expect(document.body.firstElementChild?.getAttribute('aria-label')).toBe('Atajos');
  });

  it('takes the focus to the content of the page on screen, not to a hidden one', () => {
    installSkipLink(document, TEXTS, NAV);
    const link = document.getElementById(SKIP_LINK_ID) as HTMLAnchorElement;
    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
    link.dispatchEvent(event);
    const content = document.querySelector('#shown ion-content') as HTMLElement;
    expect(event.defaultPrevented).toBe(true);
    expect(content.getAttribute('tabindex')).toBe('-1');
    expect(document.activeElement).toBe(content);
  });

  it('is installed once', () => {
    installSkipLink(document, TEXTS, NAV);
    installSkipLink(document, TEXTS, NAV);
    expect(document.querySelectorAll(`#${SKIP_LINK_ID}`)).toHaveLength(1);
  });
});
