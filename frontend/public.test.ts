// The entry of the public web (spec §8.4): `frontend/public.ts`, loaded by `{% public_assets %}` on
// every page that extends `public/public_base.html`. It registers the ion-* the templates use (from
// @ionic/core, Ionic in `ios` mode as before), brings Ionic's CSS, the @erplora/ui tokens, the fonts
// and the public stylesheets, and wires the few behaviours the OutfitKit components had in their
// shadow DOM: the navbar's mobile panel, the scroll reveal, the server messages as toasts, and
// Mermaid on demand (spec §6). No CDN, no network for icons.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

import {
  ION_COMPONENTS,
  IONIC_CONFIG,
  MERMAID_CONFIG,
  presentServerMessages,
  renderDiagrams,
  setupNavbar,
  setupReveal,
  type ToastOptions,
} from './public';

const HERE = dirname(fileURLToPath(import.meta.url));
const SAAS_DIR = join(HERE, '..');
const SOURCE = readFileSync(join(HERE, 'public.ts'), 'utf8');
const PUBLIC_TEMPLATES = join(SAAS_DIR, 'public', 'templates');
const PUBLIC_STATIC = join(SAAS_DIR, 'public', 'static', 'public');

function htmlFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return htmlFiles(path);
    return entry.name.endsWith('.html') ? [path] : [];
  });
}

/** Every ion-* tag the public templates write. */
function usedIonTags(): Set<string> {
  const used = new Set<string>();
  for (const file of htmlFiles(PUBLIC_TEMPLATES)) {
    for (const [, tag] of readFileSync(file, 'utf8').matchAll(/<(ion-[a-z-]+)/g)) used.add(tag);
  }
  return used;
}

/** The CSS this entry imports, in order, as paths relative to saas-next (or package names). */
function importedSheets(): string[] {
  return [...SOURCE.matchAll(/^import '([^']+\.css)';$/gm)].map(([, spec]) =>
    spec.startsWith('.') ? relative(SAAS_DIR, join(HERE, spec)) : spec,
  );
}

function page(html: string): Document {
  document.documentElement.className = '';
  document.body.innerHTML = html;
  return document;
}

describe('the public entry: components and styles', () => {
  it('registers every ion-* the public templates use', () => {
    const used = usedIonTags();
    expect(used.size).toBeGreaterThan(0);
    expect([...used].filter((tag) => !(tag in ION_COMPONENTS))).toEqual([]);
  });

  it('registers nothing else but ion-toast, which the server messages create (L8)', () => {
    const used = usedIonTags();
    expect(Object.keys(ION_COMPONENTS).filter((tag) => tag !== 'ion-toast' && !used.has(tag))).toEqual([]);
  });

  it('defines each component from its @ionic/core module, so only those reach the bundle', () => {
    for (const tag of Object.keys(ION_COMPONENTS)) {
      expect(SOURCE).toContain(`from '@ionic/core/components/${tag}.js';`);
    }
    // The toasts of the server messages.
    expect(ION_COMPONENTS).toHaveProperty('ion-toast');
    // ion-icon would fetch its SVG by name: the templates paint icons with {% icon %} instead.
    expect(ION_COMPONENTS).not.toHaveProperty('ion-icon');
  });

  it('keeps Ionic in ios mode, as the old public base and the shell do', () => {
    expect(IONIC_CONFIG).toEqual({ mode: 'ios' });
  });

  it("brings Ionic's CSS, the UI tokens, the fonts and the public sheets, in cascade order", () => {
    expect(importedSheets()).toEqual([
      '@ionic/core/css/core.css',
      '@ionic/core/css/normalize.css',
      '@ionic/core/css/typography.css',
      '@ionic/core/css/palettes/dark.class.css',
      'packages/ui/src/shell/theme/variables.css',
      'packages/ui/src/shell/theme/palettes.css',
      'frontend/fonts.css',
      'public/static/public/theme.css',
      'public/static/public/layout.css',
      'public/static/public/landing.css',
      'public/static/public/public-landing.css',
      'public/static/public/ionic-utilities.css',
      'public/static/public/cookie-consent-banner.css',
    ]);
    // structure.css locks the body (position: fixed) for an app shell; the public pages scroll.
    expect(SOURCE).not.toMatch(/^import '[^']*structure\.css';$/m);
  });

  it('imports every component stylesheet', () => {
    expect(SOURCE).toContain("import.meta.glob('../public/static/public/components/*.css', { eager: true })");
    expect(readdirSync(join(PUBLIC_STATIC, 'components')).filter((name) => name.endsWith('.css')).length).toBe(15);
  });

  it('never reaches a CDN', () => {
    expect(SOURCE).not.toMatch(/https?:\/\//);
  });
});

describe('the navbar panel', () => {
  // Native buttons (L8): Ionic 8.8.9 copies an ion-button host's aria-* to its inner button once
  // and never follows aria-expanded, so the burger and the close button are plain <button>s.
  const NAVBAR = `
    <nav class="ep-navbar" data-navbar>
      <button type="button" class="ep-navbar__burger" data-navbar-toggle aria-expanded="false" aria-controls="ep-navbar-panel">menu</button>
      <div id="ep-navbar-panel" data-navbar-panel>
        <div class="ep-navbar__panel-head">
          <button type="button" class="ep-navbar__close" data-navbar-close>close</button>
        </div>
        <div class="ep-navbar__links"><a href="/features/">Features</a></div>
      </div>
      <div data-navbar-close class="ep-navbar__backdrop"></div>
    </nav>`;

  function opened() {
    const doc = page(NAVBAR);
    setupNavbar(doc);
    doc.querySelector<HTMLElement>('[data-navbar-toggle]')!.click();
    return doc;
  }

  it('opens from the burger and says so to assistive technology', () => {
    const doc = opened();
    expect(doc.querySelector('[data-navbar]')!.hasAttribute('data-open')).toBe(true);
    expect(doc.querySelector('[data-navbar-toggle]')!.getAttribute('aria-expanded')).toBe('true');
    expect(doc.documentElement.classList.contains('ep-navbar-open')).toBe(true);
  });

  it('closes with the close button, the backdrop, Escape and a link', () => {
    const closers: Array<(doc: Document) => void> = [
      (doc) => doc.querySelector<HTMLElement>('button[data-navbar-close]')!.click(),
      (doc) => doc.querySelector<HTMLElement>('.ep-navbar__backdrop')!.click(),
      (doc) => doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })),
      (doc) => doc.querySelector<HTMLElement>('.ep-navbar__links a')!.click(),
    ];
    for (const close of closers) {
      const doc = opened();
      close(doc);
      expect(doc.querySelector('[data-navbar]')!.hasAttribute('data-open')).toBe(false);
      expect(doc.querySelector('[data-navbar-toggle]')!.getAttribute('aria-expanded')).toBe('false');
      expect(doc.documentElement.classList.contains('ep-navbar-open')).toBe(false);
    }
  });

  it('takes the focus to the close button and gives it back to the burger', () => {
    const doc = opened();
    expect(doc.activeElement).toBe(doc.querySelector('button[data-navbar-close]'));

    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(doc.activeElement).toBe(doc.querySelector('button[data-navbar-toggle]'));
  });

  it('does nothing on a page without the navbar (the 500 page)', () => {
    expect(() => setupNavbar(page('<main></main>'))).not.toThrow();
  });
});

describe('the scroll reveal', () => {
  const REVEALS = `
    <div class="ep-reveal" data-reveal="up" data-reveal-delay="80">a</div>
    <div class="ep-reveal" data-reveal="left">b</div>`;

  it('reveals each block when it enters the viewport, with its delay, once', () => {
    const observed: Element[] = [];
    let callback: IntersectionObserverCallback = () => undefined;
    const unobserve = vi.fn();
    class FakeObserver {
      constructor(cb: IntersectionObserverCallback, readonly options: IntersectionObserverInit) {
        callback = cb;
        expect(options).toEqual({ threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
      }
      observe(element: Element) {
        observed.push(element);
      }
      unobserve = unobserve;
      disconnect() {}
    }
    const doc = page(REVEALS);

    setupReveal(doc, FakeObserver as unknown as typeof IntersectionObserver);
    const [first, second] = observed as HTMLElement[];
    callback(
      [{ target: first, isIntersecting: true } as unknown as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );

    expect(observed).toHaveLength(2);
    expect(first.style.getPropertyValue('--ep-reveal-delay')).toBe('80ms');
    expect(first.classList.contains('is-revealed')).toBe(true);
    expect(second.classList.contains('is-revealed')).toBe(false);
    expect(unobserve).toHaveBeenCalledWith(first);
  });

  it('shows everything at once without IntersectionObserver', () => {
    const doc = page(REVEALS);

    setupReveal(doc, undefined);

    expect(doc.querySelectorAll('.ep-reveal.is-revealed')).toHaveLength(2);
  });
});

describe('the server messages', () => {
  const MESSAGES = `
    <div data-server-messages>
      <div data-level="success"><div class="ep-inline-feedback__body">Message sent</div></div>
      <div data-level="error"><div class="ep-inline-feedback__body">Something failed</div></div>
      <div data-level="info"><div class="ep-inline-feedback__body">Note</div></div>
    </div>`;

  it('turns each inline message into a toast of its colour and removes the list', () => {
    const toasts: ToastOptions[] = [];
    const doc = page(MESSAGES);

    presentServerMessages(doc, (options) => toasts.push(options));

    expect(toasts).toEqual([
      expect.objectContaining({ message: 'Message sent', color: 'success' }),
      expect.objectContaining({ message: 'Something failed', color: 'danger' }),
      expect.objectContaining({ message: 'Note', color: 'primary' }),
    ]);
    expect(doc.querySelector('[data-server-messages]')).toBeNull();
  });

  it('leaves the page alone without messages', () => {
    const present = vi.fn();
    presentServerMessages(page('<main></main>'), present);
    expect(present).not.toHaveBeenCalled();
  });
});

describe('Mermaid on demand (spec §6)', () => {
  it('is not even loaded on a page without diagrams', async () => {
    const load = vi.fn();
    expect(await renderDiagrams(page('<pre><code>x</code></pre>'), load)).toBe(false);
    expect(load).not.toHaveBeenCalled();
  });

  it('renders the pre.mermaid blocks with strict security and no auto start', async () => {
    const mermaid = { initialize: vi.fn(), run: vi.fn().mockResolvedValue(undefined) };
    const doc = page('<pre class="mermaid">graph TD; A --- B</pre>');

    expect(await renderDiagrams(doc, async () => ({ default: mermaid }))).toBe(true);

    expect(MERMAID_CONFIG).toEqual({ startOnLoad: false, securityLevel: 'strict' });
    expect(mermaid.initialize).toHaveBeenCalledWith(MERMAID_CONFIG);
    expect(mermaid.run).toHaveBeenCalledWith({ nodes: [doc.querySelector('pre.mermaid')] });
  });

  it('leaves the diagram source readable and logs when Mermaid fails', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const doc = page('<pre class="mermaid">graph TD; A --- B</pre>');
    const mermaid = { initialize: vi.fn(), run: vi.fn().mockRejectedValue(new Error('parse error')) };

    expect(await renderDiagrams(doc, async () => ({ default: mermaid }))).toBe(false);

    expect(doc.querySelector('pre.mermaid')!.textContent).toBe('graph TD; A --- B');
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });
});
