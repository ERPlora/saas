// «Skip to content» (audit 2026-10-14, R-11; W-01 of the mockups): before the content of a panel page there are
// six or seven stops of the keyboard (the user, the menu's entries, the brand, Back). The shell (`@erplora/ui`)
// has no skip link yet (docs/UI-REQUESTS-panel.md), so the entry puts one first in `<body>`: hidden until it has
// the focus (`panel-chrome.css`), it takes the focus to the page on screen — Ionic keeps the pages it leaves in
// the outlet, hidden with `ion-page-hidden` — on its `ion-content`. Its text follows `<html lang>`, which the
// shell keeps in step with the account's language.

export const SKIP_LINK_ID = 'skip-to-content';

/** The link's text per language; English for any other. */
export type SkipLinkTexts = { en: string } & Record<string, string>;

/** The content of the page on screen: the last visible `.ion-page` of the outlet. */
function shownContent(doc: Document): HTMLElement | null {
  const pages = [...doc.querySelectorAll<HTMLElement>('ion-router-outlet .ion-page:not(.ion-page-hidden)')];
  const page = pages.at(-1) ?? null;
  return (page ?? doc).querySelector<HTMLElement>('ion-content');
}

export function installSkipLink(doc: Document, texts: SkipLinkTexts): void {
  if (doc.getElementById(SKIP_LINK_ID)) return;
  const link = doc.createElement('a');
  link.id = SKIP_LINK_ID;
  link.className = 'skip-link';
  link.href = '#main';
  const paint = () => {
    const language = (doc.documentElement.lang || 'en').split('-')[0].toLowerCase();
    link.textContent = texts[language] ?? texts.en;
  };
  paint();
  new MutationObserver(paint).observe(doc.documentElement, { attributes: true, attributeFilter: ['lang'] });
  link.addEventListener('click', (event) => {
    const content = shownContent(doc);
    if (!content) return;
    event.preventDefault();
    content.setAttribute('tabindex', '-1');
    content.focus();
  });
  doc.body.prepend(link);
}
