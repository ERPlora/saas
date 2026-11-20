// The entry of the public web: `frontend/public.ts`, loaded by `{% public_assets %}` on every page
// that extends `public/public_base.html`. It registers the ion-* the templates use (from @ionic/core,
// Ionic in `ios` mode), brings Ionic's CSS, the @erplora/ui tokens, the fonts and the public
// stylesheets, and wires a few behaviours: the scroll reveal, the server messages as toasts, and
// Mermaid on demand. No CDN, no network for icons. It also keeps the page in the colour mode the
// server wrote on <html> (`data-ep-theme`, the account's, as the panel paints it), and in `system`
// follows the operating system live. The navbar's mobile panel is not in the module (saas#243): its
// contract runs the inline script of public/partials/navbar.html in public.navbar.test.ts.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DARK_QUERY,
  ION_COMPONENTS,
  IONIC_CONFIG,
  MERMAID_CONFIG,
  presentServerMessages,
  renderDiagrams,
  setupAppBack,
  setupColorScheme,
  setupReveal,
  type ToastOptions,
} from './public';
import { page, PUBLIC_TEMPLATES, SAAS_DIR, SOURCE } from './__tests__/public-entry';

const HERE = dirname(fileURLToPath(import.meta.url));
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

/** The CSS this entry imports, in order, as paths relative to the SaaS's root (or package names). */
function importedSheets(): string[] {
  return [...SOURCE.matchAll(/^import '([^']+\.css)';$/gm)].map(([, spec]) =>
    spec.startsWith('.') ? relative(SAAS_DIR, join(HERE, spec)) : spec,
  );
}

describe('the public entry: components and styles', () => {
  it('registers every ion-* the public templates use', () => {
    const used = usedIonTags();
    expect(used.size).toBeGreaterThan(0);
    expect([...used].filter((tag) => !(tag in ION_COMPONENTS))).toEqual([]);
  });

  it('registers nothing else but ion-toast, which the server messages create', () => {
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
      'packages/ui/src/shell/theme/brand.css',
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

  it('uses the current brand blue and shared geometry in the public chrome', () => {
    const base = readFileSync(join(PUBLIC_TEMPLATES, 'public', 'public_base.html'), 'utf8');
    const buttons = readFileSync(join(PUBLIC_STATIC, 'components', 'button.css'), 'utf8');
    expect(base).toContain('<meta name="theme-color" content="#1496d6">');
    expect(buttons.match(/--border-radius: var\(--ep-radius-sm\);/g)).toHaveLength(3);
    expect(buttons).not.toContain('--border-radius: var(--ep-radius-lg);');
  });

  it('imports every component stylesheet', () => {
    expect(SOURCE).toContain("import.meta.glob('../public/static/public/components/*.css', { eager: true })");
    expect(readdirSync(join(PUBLIC_STATIC, 'components')).filter((name) => name.endsWith('.css')).length).toBe(17);
  });

  it('never reaches a CDN', () => {
    expect(SOURCE).not.toMatch(/https?:\/\//);
  });

  it('stacks the open side menu above the cookie notice, which otherwise lies over its last buttons (saas#244)', () => {
    // The real measure is public-cookie-notice.spec.ts, which the CI does not run: this keeps the order in the CI.
    const sheet = (name: string) => readFileSync(join(PUBLIC_STATIC, name), 'utf8');
    const open = /\.ep-navbar\[data-open\]\s*\{[^}]*z-index:\s*(\d+)/.exec(sheet('components/navbar.css'));
    const notice = /#cookie-consent-banner\s*\{[^}]*z-index:\s*(\d+)/.exec(sheet('cookie-consent-banner.css'));
    expect(Number(open?.[1])).toBeGreaterThan(Number(notice?.[1]));
  });
});

/** A `prefers-color-scheme: dark` query the test flips, as the operating system would. */
function fakeSystem(dark: boolean) {
  const listeners: Array<(event: MediaQueryListEvent) => void> = [];
  const media = {
    matches: dark,
    media: DARK_QUERY,
    addEventListener: (_type: 'change', listener: (event: MediaQueryListEvent) => void) => listeners.push(listener),
  };
  const matchMedia = vi.fn((query: string) => {
    expect(query).toBe(DARK_QUERY);
    return media as unknown as MediaQueryList;
  });
  return {
    matchMedia,
    flip(nowDark: boolean) {
      media.matches = nowDark;
      for (const listener of listeners) listener({ matches: nowDark } as MediaQueryListEvent);
    },
  };
}

/** The page as the server wrote it: `data-ep-theme` on <html> (absent on a page that forgot it). */
function themed(mode: string | null, system: ReturnType<typeof fakeSystem>): Document {
  const doc = page('<main></main>');
  if (mode === null) doc.documentElement.removeAttribute('data-ep-theme');
  else doc.documentElement.setAttribute('data-ep-theme', mode);
  vi.spyOn(doc.defaultView!, 'matchMedia').mockImplementation(system.matchMedia);
  return doc;
}

const isDark = (doc: Document) => doc.documentElement.classList.contains('ion-palette-dark');

describe('the colour mode', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.documentElement.removeAttribute('data-ep-theme');
  });

  it('follows a dark system in system mode', () => {
    const doc = themed('system', fakeSystem(true));

    setupColorScheme(doc);

    expect(isDark(doc)).toBe(true);
  });

  it('stays light on a light system in system mode, even if the class was left on <html>', () => {
    const doc = themed('system', fakeSystem(false));
    doc.documentElement.classList.add('ion-palette-dark');

    setupColorScheme(doc);

    expect(isDark(doc)).toBe(false);
  });

  it('treats a page without the attribute as system mode', () => {
    const doc = themed(null, fakeSystem(true));

    setupColorScheme(doc);

    expect(isDark(doc)).toBe(true);
  });

  it("gives the account's explicit choice priority over the system", () => {
    const light = themed('light', fakeSystem(true));
    setupColorScheme(light);
    expect(isDark(light)).toBe(false);

    const dark = themed('dark', fakeSystem(false));
    setupColorScheme(dark);
    expect(isDark(dark)).toBe(true);
  });

  it('reacts live when the system changes, in system mode', () => {
    const system = fakeSystem(false);
    const doc = themed('system', system);
    setupColorScheme(doc);

    system.flip(true);
    expect(isDark(doc)).toBe(true);

    system.flip(false);
    expect(isDark(doc)).toBe(false);
  });

  it('ignores the system changing when the account chose a mode', () => {
    const system = fakeSystem(false);
    const doc = themed('light', system);
    setupColorScheme(doc);

    system.flip(true);

    expect(isDark(doc)).toBe(false);
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

describe('Mermaid on demand', () => {
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
    // The theme of the page's colour mode: Mermaid's own on a light page.
    expect(mermaid.initialize).toHaveBeenCalledWith({ ...MERMAID_CONFIG, theme: 'default' });
    expect(mermaid.run).toHaveBeenCalledWith({ nodes: [doc.querySelector('pre.mermaid')] });
  });

  it("draws with Mermaid's dark theme on a dark page", async () => {
    const mermaid = { initialize: vi.fn(), run: vi.fn().mockResolvedValue(undefined) };
    const doc = page('<pre class="mermaid">graph TD; A --- B</pre>');
    doc.documentElement.classList.add('ion-palette-dark');

    await renderDiagrams(doc, async () => ({ default: mermaid }));

    expect(mermaid.initialize).toHaveBeenCalledWith({ ...MERMAID_CONFIG, theme: 'dark' });
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

describe('setupAppBack: «Back» of a page opened from the installed app (PUBLIC-F26)', () => {
  // As public/partials/app_bar.html renders it: a real link, so it works before this script runs (saas#236).
  const BAR =
    '<header class="ep-app-bar"><a class="ep-app-bar__back" href="/shell/?surface=desktop" data-app-back>Back</a></header>';

  function click(doc: Document): MouseEvent {
    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
    doc.querySelector('[data-app-back]')!.dispatchEvent(event);
    return event;
  }

  it('goes back to the app screen that opened the page', () => {
    const back = vi.fn();
    const doc = page(BAR);
    setupAppBack(doc, { length: 3, back });

    const event = click(doc);

    expect(back).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  it('without a history (the page opened alone) it follows its link to the app start', () => {
    const back = vi.fn();
    const doc = page(BAR);
    setupAppBack(doc, { length: 1, back });

    const event = click(doc);

    expect(back).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it('does nothing on a page of the web, which has no such bar', () => {
    expect(() => setupAppBack(page('<nav class="ep-navbar"></nav>'), { length: 3, back: vi.fn() })).not.toThrow();
  });

  it('runs at boot', () => {
    expect(SOURCE).toMatch(/export function boot\(doc: Document\): void \{[^}]*setupAppBack\(doc\)/);
  });
});

describe('the door of a demo being prepared (frontend/demo-wait.ts)', () => {
  it('waits for the demo at boot', () => {
    expect(SOURCE).toMatch(/export function boot\(doc: Document\): void \{[^}]*waitForDemo\(doc\)/);
  });
});

describe('reCAPTCHA on the public forms (frontend/recaptcha.ts)', () => {
  it('protects the contact form and the demo at boot', () => {
    expect(SOURCE).toMatch(/export function boot\(doc: Document\): void \{[^}]*protectForms\(doc\)/);
  });

  it('carries no CSS of Google’s badge: frontend/recaptcha.ts hides it only with Google’s script (off by default)', () => {
    // Its notice is under each protected form (public/partials/recaptcha_notice.html), only while reCAPTCHA is on.
    for (const sheet of ['landing.css', 'public-landing.css']) {
      const css = readFileSync(join(SAAS_DIR, 'public', 'static', 'public', sheet), 'utf8');
      expect(css, sheet).not.toContain('grecaptcha-badge');
    }
  });
});
