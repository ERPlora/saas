// Entry of the public web of erplora.com (spec §8.4; `build.rollupOptions.input` in vite.config.ts,
// loaded by `{% public_assets %}` in public/templates/public/public_base.html). The pages are Django
// templates (SEO); this file gives them what the old base took from vendored files and a CDN:
//   - the ion-* the templates use, registered one by one from @ionic/core (Ionic in `ios` mode, as
//     the old base and the shell pin it) — guard: public.test.ts reads the templates;
//   - Ionic's CSS (no structure.css: these pages scroll the document), the @erplora/ui tokens and
//     palettes, IBM Plex, and the stylesheets of public/static/public/;
//   - the behaviour the OutfitKit components carried in their shadow DOM: the navbar's mobile
//     panel, the scroll reveal, and the server messages as ion-toasts;
//   - the colour mode: the one the server wrote on <html> (`data-ep-theme`), and in `system` the
//     operating system's, followed live (the head's inline script already painted the first frame);
//   - Mermaid, imported only when the page has a `pre.mermaid` (spec §6).
// No CDN and no runtime icon fetch: icons are SVG painted on the server by `{% icon %}`.
import '@ionic/core/css/core.css';
import '@ionic/core/css/normalize.css';
import '@ionic/core/css/typography.css';
import '@ionic/core/css/palettes/dark.class.css';
import '../packages/ui/src/shell/theme/variables.css';
import '../packages/ui/src/shell/theme/palettes.css';
import './fonts.css';
import '../public/static/public/theme.css';
import '../public/static/public/layout.css';
import '../public/static/public/landing.css';
import '../public/static/public/public-landing.css';
import '../public/static/public/ionic-utilities.css';
import '../public/static/public/cookie-consent-banner.css';

import { initialize } from '@ionic/core/components';
import { defineCustomElement as defineAccordion } from '@ionic/core/components/ion-accordion.js';
import { defineCustomElement as defineAccordionGroup } from '@ionic/core/components/ion-accordion-group.js';
import { defineCustomElement as defineButton } from '@ionic/core/components/ion-button.js';
import { defineCustomElement as defineCard } from '@ionic/core/components/ion-card.js';
import { defineCustomElement as defineCardContent } from '@ionic/core/components/ion-card-content.js';
import { defineCustomElement as defineCardHeader } from '@ionic/core/components/ion-card-header.js';
import { defineCustomElement as defineCardTitle } from '@ionic/core/components/ion-card-title.js';
import { defineCustomElement as defineChip } from '@ionic/core/components/ion-chip.js';
import { defineCustomElement as defineInput } from '@ionic/core/components/ion-input.js';
import { defineCustomElement as defineItem } from '@ionic/core/components/ion-item.js';
import { defineCustomElement as defineLabel } from '@ionic/core/components/ion-label.js';
import { defineCustomElement as defineList } from '@ionic/core/components/ion-list.js';
import { defineCustomElement as defineNote } from '@ionic/core/components/ion-note.js';
import { defineCustomElement as defineSearchbar } from '@ionic/core/components/ion-searchbar.js';
import { defineCustomElement as defineTextarea } from '@ionic/core/components/ion-textarea.js';
import { defineCustomElement as defineToast } from '@ionic/core/components/ion-toast.js';
import { defineCustomElement as defineToggle } from '@ionic/core/components/ion-toggle.js';

// One stylesheet per component partial of public/templates/public/components/ (and the hero,
// navbar and footer partials).
import.meta.glob('../public/static/public/components/*.css', { eager: true });

/** Ionic's global config: `ios`, as `window.Ionic = { config: { mode: 'ios' } }` set it before. */
export const IONIC_CONFIG = { mode: 'ios' } as const;

/**
 * The ion-* of the public templates (and ion-toast for the server messages), and nothing else: each
 * one is bundled. Each define also registers the components it renders inside (ion-icon for an
 * accordion's chevron, ion-ripple-effect). A template that uses another one must add it here, and
 * one that stops using it must take it out: public.test.ts fails until it does.
 */
export const ION_COMPONENTS: Record<string, () => void> = {
  'ion-accordion': defineAccordion,
  'ion-accordion-group': defineAccordionGroup,
  'ion-button': defineButton,
  'ion-card': defineCard,
  'ion-card-content': defineCardContent,
  'ion-card-header': defineCardHeader,
  'ion-card-title': defineCardTitle,
  'ion-chip': defineChip,
  'ion-input': defineInput,
  'ion-item': defineItem,
  'ion-label': defineLabel,
  'ion-list': defineList,
  'ion-note': defineNote,
  'ion-searchbar': defineSearchbar,
  'ion-textarea': defineTextarea,
  'ion-toast': defineToast,
  'ion-toggle': defineToggle,
};

export function registerIonic(): void {
  initialize(IONIC_CONFIG);
  for (const define of Object.values(ION_COMPONENTS)) define();
}

// --- Colour mode (public/public_base.html) ----------------------------------------------------

/** The system's dark preference, as the shell reads it (`packages/ui/src/shell/theme.ts`). */
export const DARK_QUERY = '(prefers-color-scheme: dark)';

/**
 * Keeps <html> in the colour mode the server wrote: `data-ep-theme` is the account's mode (Account →
 * Preferences, the one the panel paints; `base.context_processors.theme`), `system` for a visitor.
 * `light` and `dark` are fixed; `system` (or no attribute) follows `prefers-color-scheme` and its
 * changes, live. Dark is Ionic's `ion-palette-dark` class, the shell's contract.
 */
export function setupColorScheme(doc: Document): void {
  const root = doc.documentElement;
  const mode = root.getAttribute('data-ep-theme');
  const system = doc.defaultView?.matchMedia?.(DARK_QUERY);
  const apply = () =>
    root.classList.toggle('ion-palette-dark', mode === 'dark' || (mode !== 'light' && Boolean(system?.matches)));
  apply();
  if (mode !== 'light' && mode !== 'dark') system?.addEventListener?.('change', apply);
}

// --- Navbar (public/partials/navbar.html) -----------------------------------------------------

/** The navbar's side panel at 800 px and below: burger, close button, backdrop, Esc and links. */
export function setupNavbar(doc: Document): void {
  const navbar = doc.querySelector<HTMLElement>('[data-navbar]');
  const toggle = navbar?.querySelector<HTMLButtonElement>('button[data-navbar-toggle]');
  const panel = navbar?.querySelector<HTMLElement>('[data-navbar-panel]');
  if (!navbar || !toggle || !panel) return;

  const isOpen = () => navbar.hasAttribute('data-open');
  const setOpen = (open: boolean) => {
    navbar.toggleAttribute('data-open', open);
    // A native <button> (L8): an ion-button would keep the aria-expanded it had when it loaded.
    toggle.setAttribute('aria-expanded', String(open));
    doc.documentElement.classList.toggle('ep-navbar-open', open);
  };
  const close = () => {
    if (!isOpen()) return;
    const hadFocus = panel.contains(doc.activeElement);
    setOpen(false);
    if (hadFocus) toggle.focus();
  };

  toggle.addEventListener('click', () => {
    setOpen(!isOpen());
    // The close button comes first in the panel: the focus lands on it, as in a side sheet.
    if (isOpen()) panel.querySelector<HTMLElement>('button, a, ion-button')?.focus();
  });
  for (const closer of navbar.querySelectorAll<HTMLElement>('[data-navbar-close]')) {
    closer.addEventListener('click', close);
  }
  panel.addEventListener('click', (event) => {
    if ((event.target as Element | null)?.closest('a')) close();
  });
  doc.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });
  // Back to the desktop bar with the panel open: the links return to the bar, nothing stays locked.
  doc.defaultView?.matchMedia?.('(min-width: 801px)').addEventListener?.('change', (event) => {
    if (event.matches) close();
  });
}

// --- Scroll reveal (public/components/reveal.html) --------------------------------------------

/** Adds `is-revealed` to each `.ep-reveal` once it enters the viewport (port of ok-reveal). */
export function setupReveal(doc: Document, Observer: typeof IntersectionObserver | undefined): void {
  const blocks = [...doc.querySelectorAll<HTMLElement>('.ep-reveal[data-reveal]')];
  for (const block of blocks) {
    const delay = Number(block.dataset.revealDelay);
    if (delay > 0) block.style.setProperty('--ep-reveal-delay', `${delay}ms`);
  }
  if (!Observer) {
    for (const block of blocks) block.classList.add('is-revealed');
    return;
  }
  const observer = new Observer(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-revealed');
        observer.unobserve(entry.target);
      }
    },
    { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
  );
  for (const block of blocks) observer.observe(block);
}

// --- Server messages (public/partials/messages.html) ------------------------------------------

export type ToastOptions = { message: string; color: string; duration: number; position: 'top' };

/** Django's message levels → Ionic colours. */
const LEVEL_COLORS: Record<string, string> = {
  success: 'success',
  error: 'danger',
  warning: 'warning',
  info: 'primary',
  debug: 'medium',
};

function presentToast(doc: Document, options: ToastOptions): void {
  const toast = Object.assign(doc.createElement('ion-toast'), options);
  doc.body.appendChild(toast);
  void (toast as HTMLElement & { present(): Promise<void> }).present();
}

/** Each inline message becomes a toast; the inline list (the no-JavaScript reading) goes away. */
export function presentServerMessages(
  doc: Document,
  present: (options: ToastOptions) => void = (options) => presentToast(doc, options),
): void {
  const region = doc.querySelector('[data-server-messages]');
  if (!region) return;
  for (const item of region.querySelectorAll<HTMLElement>('[data-level]')) {
    const message = item.querySelector('.ep-inline-feedback__body')?.textContent?.trim() ?? '';
    if (!message) continue;
    present({ message, color: LEVEL_COLORS[item.dataset.level ?? ''] ?? 'primary', duration: 6000, position: 'top' });
  }
  region.remove();
}

// --- Mermaid (spec §6) ------------------------------------------------------------------------

export const MERMAID_CONFIG = { startOnLoad: false, securityLevel: 'strict' } as const;

type MermaidConfig = typeof MERMAID_CONFIG & { theme: 'default' | 'dark' };

type MermaidModule = {
  default: { initialize(config: MermaidConfig): void; run(options: { nodes: HTMLElement[] }): Promise<void> };
};

/**
 * Renders the `pre.mermaid` blocks of `live.markdown`'s HTML. Mermaid is loaded only when the page
 * has one. If it fails, the diagram's source stays readable and the error goes to the console.
 */
export async function renderDiagrams(
  doc: Document,
  load: () => Promise<MermaidModule> = () => import('mermaid') as unknown as Promise<MermaidModule>,
): Promise<boolean> {
  const nodes = [...doc.querySelectorAll<HTMLElement>('pre.mermaid')];
  if (nodes.length === 0) return false;
  try {
    const { default: mermaid } = await load();
    // Drawn once, in the page's colour mode at that moment.
    const dark = doc.documentElement.classList.contains('ion-palette-dark');
    mermaid.initialize({ ...MERMAID_CONFIG, theme: dark ? 'dark' : 'default' });
    await mermaid.run({ nodes });
    return true;
  } catch (error) {
    console.error('public: Mermaid could not render the diagrams', error);
    return false;
  }
}

// --- The app bar (public/partials/app_bar.html, PUBLIC-F26) -----------------------------------------

/** What `setupAppBack` reads of the browser's history. */
export type BackHistory = Pick<History, 'length' | 'back'>;

/**
 * «Back» of a public page opened from the installed app: the app screen that opened it is the previous entry of
 * the history, so it goes back there. Without one (the page opened alone) the link's own address, the app's
 * start, is followed.
 */
export function setupAppBack(doc: Document, history: BackHistory | undefined = doc.defaultView?.history): void {
  doc.querySelector<HTMLElement>('[data-app-back]')?.addEventListener('click', (event) => {
    if (!history || history.length <= 1) return;
    event.preventDefault();
    history.back();
  });
}

// --- Boot -------------------------------------------------------------------------------------

export function boot(doc: Document): void {
  setupColorScheme(doc);
  registerIonic();
  setupNavbar(doc);
  setupAppBack(doc);
  setupReveal(doc, doc.defaultView?.IntersectionObserver);
  presentServerMessages(doc);
  void renderDiagrams(doc);
}

boot(document);
