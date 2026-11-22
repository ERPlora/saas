// The navbar's mobile panel of the public web. It is not in `frontend/public.ts` (saas#243): it is the inline script
// of public/partials/navbar.html, which runs as the page is parsed, and these tests run that very script.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { page, PUBLIC_TEMPLATES, SOURCE } from './__tests__/public-entry';

describe('the navbar panel', () => {
  // Native buttons: Ionic 8.8.9 copies an ion-button host's aria-* to its inner button once
  // and never follows aria-expanded, so the burger and the close button are plain <button>s.
  const NAVBAR = `
    <nav class="ep-navbar" data-navbar>
      <a class="ep-navbar__brand" href="/">ERPlora</a>
      <button type="button" class="ep-navbar__burger" data-navbar-toggle aria-expanded="false" aria-controls="ep-navbar-panel">menu</button>
      <div id="ep-navbar-panel" data-navbar-panel>
        <div class="ep-navbar__panel-head">
          <button type="button" class="ep-navbar__close" data-navbar-close>close</button>
        </div>
        <div class="ep-navbar__links"><a href="/features/">Features</a></div>
      </div>
      <div data-navbar-close class="ep-navbar__backdrop"></div>
    </nav>
    <main><a href="/behind/">Behind</a></main>`;

  // The script listens on the one document of this file, so a run outlives its test: closed, it leaves the next run's keys alone.
  afterEach(() => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
  });

  /** The script the partial writes after the navbar: it runs as the page is parsed, with no module (saas#243). */
  function inlineScript(): string {
    const partial = readFileSync(join(PUBLIC_TEMPLATES, 'public', 'partials', 'navbar.html'), 'utf8');
    const script = /<script nonce="\{\{ csp_nonce \}\}">([\s\S]*?)<\/script>/.exec(partial);
    expect(script, 'navbar.html has no inline script').not.toBeNull();
    return script![1];
  }

  /** A window as wide as `wide` says, whose width can change: what the script's `(min-width: 801px)` listens to. */
  function fakeWindowWidth(wide = false) {
    const listeners: Array<(event: MediaQueryListEvent) => void> = [];
    vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => {
      expect(query).toBe('(min-width: 801px)');
      return {
        matches: wide,
        media: query,
        addEventListener: (_type: 'change', listener: (event: MediaQueryListEvent) => void) => listeners.push(listener),
      } as unknown as MediaQueryList;
    });
    return (matches: boolean) => {
      for (const listener of listeners) listener({ matches } as MediaQueryListEvent);
    };
  }

  function loaded() {
    const doc = page(NAVBAR);
    const resize = fakeWindowWidth();
    // The template's own script, run as the browser would.
    new Function(inlineScript())();
    return { doc, resize };
  }

  function opened() {
    const { doc, resize } = loaded();
    doc.querySelector<HTMLElement>('[data-navbar-toggle]')!.click();
    return { doc, resize };
  }

  function expectClosed(doc: Document) {
    expect(doc.querySelector('[data-navbar]')!.hasAttribute('data-open')).toBe(false);
    expect(doc.querySelector('[data-navbar-toggle]')!.getAttribute('aria-expanded')).toBe('false');
    expect(doc.documentElement.classList.contains('ep-navbar-open')).toBe(false);
  }

  it('opens from the burger and says so to assistive technology', () => {
    const { doc } = opened();
    expect(doc.querySelector('[data-navbar]')!.hasAttribute('data-open')).toBe(true);
    expect(doc.querySelector('[data-navbar-toggle]')!.getAttribute('aria-expanded')).toBe('true');
    expect(doc.documentElement.classList.contains('ep-navbar-open')).toBe(true);
  });

  it('closes with the close button, the backdrop, Escape, a link and the burger again', () => {
    const closers: Array<(doc: Document) => void> = [
      (doc) => doc.querySelector<HTMLElement>('button[data-navbar-close]')!.click(),
      (doc) => doc.querySelector<HTMLElement>('.ep-navbar__backdrop')!.click(),
      (doc) => doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })),
      (doc) => doc.querySelector<HTMLElement>('.ep-navbar__links a')!.click(),
      (doc) => doc.querySelector<HTMLElement>('[data-navbar-toggle]')!.click(),
    ];
    for (const close of closers) {
      const { doc } = opened();
      close(doc);
      expectClosed(doc);
    }
  });

  it('closes when the window grows to the desktop bar, and not when it shrinks', () => {
    const { doc, resize } = opened();
    resize(false);
    expect(doc.querySelector('[data-navbar]')!.hasAttribute('data-open')).toBe(true);

    resize(true);

    expectClosed(doc);
  });

  it('takes the focus to the close button and gives it back to the burger', () => {
    const { doc } = opened();
    expect(doc.activeElement).toBe(doc.querySelector('button[data-navbar-close]'));

    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(doc.activeElement).toBe(doc.querySelector('button[data-navbar-toggle]'));
  });

  it('leaves the focus where it is when it closes with the focus outside the panel', () => {
    const { doc } = opened();
    const outside = doc.body.appendChild(doc.createElement('button'));
    outside.focus();

    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(doc.activeElement).toBe(outside);
  });

  /** A key press on the page: true when the script took it over, so the browser does not move the focus on its own. */
  function pressTab(doc: Document, shiftKey = false): boolean {
    const press = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, cancelable: true });
    doc.dispatchEvent(press);
    return press.defaultPrevented;
  }

  it('goes round with Tab: from the last stop to the first, and with Shift from the first to the last', () => {
    const { doc } = opened();
    const first = doc.querySelector<HTMLElement>('button[data-navbar-close]')!;
    const last = doc.querySelector<HTMLElement>('.ep-navbar__links a')!;

    expect(pressTab(doc, true)).toBe(true);
    expect(doc.activeElement).toBe(last);

    expect(pressTab(doc)).toBe(true);
    expect(doc.activeElement).toBe(first);
  });

  it('leaves to the browser a Tab between two stops of the panel', () => {
    const { doc } = opened();

    expect(pressTab(doc)).toBe(false);
    expect(doc.activeElement).toBe(doc.querySelector('button[data-navbar-close]'));
  });

  it('brings a focus that is off the panel back to it, on either side', () => {
    const { doc } = opened();
    (doc.activeElement as HTMLElement).blur();
    expect(pressTab(doc, true)).toBe(true);
    expect(doc.activeElement).toBe(doc.querySelector('.ep-navbar__links a'));

    (doc.activeElement as HTMLElement).blur();
    expect(pressTab(doc)).toBe(true);
    expect(doc.activeElement).toBe(doc.querySelector('button[data-navbar-close]'));
  });

  it('does not touch Tab while it is closed', () => {
    const { doc } = loaded();
    const behind = doc.querySelector<HTMLElement>('main a')!;
    behind.focus();

    expect(pressTab(doc)).toBe(false);
    expect(doc.activeElement).toBe(behind);
  });

  it('keeps the rest of the page inert only while it is open, and the navbar never', () => {
    const { doc, resize } = opened();
    const main = doc.querySelector('main')!;
    const navbar = doc.querySelector('[data-navbar]')!;
    expect(main.hasAttribute('inert')).toBe(true);
    expect(navbar.hasAttribute('inert')).toBe(false);

    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(main.hasAttribute('inert')).toBe(false);

    doc.querySelector<HTMLElement>('[data-navbar-toggle]')!.click();
    expect(main.hasAttribute('inert')).toBe(true);
    resize(true);
    expect(main.hasAttribute('inert')).toBe(false);
  });

  it('keeps the brand and the burger inert while it is open: the panel and the backdrop cover them', () => {
    const { doc } = opened();
    const brand = doc.querySelector('.ep-navbar__brand')!;
    const burger = doc.querySelector('[data-navbar-toggle]')!;
    expect(brand.hasAttribute('inert')).toBe(true);
    expect(burger.hasAttribute('inert')).toBe(true);

    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(brand.hasAttribute('inert')).toBe(false);
    expect(burger.hasAttribute('inert')).toBe(false);
    expect(doc.activeElement).toBe(burger);
  });

  /** What the page sends after the navbar on a slow connection: the parser adds it to the body as it arrives. */
  async function arrives(doc: Document): Promise<HTMLElement> {
    const late = doc.createElement('footer');
    doc.body.append(late);
    await new Promise((resolve) => setTimeout(resolve));
    return late;
  }

  it('keeps inert what arrives with it open, and lets it go when it closes', async () => {
    const { doc } = opened();
    const late = await arrives(doc);
    expect(late.hasAttribute('inert')).toBe(true);

    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(late.hasAttribute('inert')).toBe(false);
  });

  it('neither opens nor marks anything when the page arrives with it closed', async () => {
    const { doc } = loaded();
    const late = await arrives(doc);
    expect(late.hasAttribute('inert')).toBe(false);
    expectClosed(doc);
  });

  it('is the only one that binds the burger: the page script answering the same press would close it', () => {
    expect(SOURCE).not.toMatch(/data-navbar|setupNavbar/);
  });
});
