/**
 * What an action button paints and says. One that is only its icon paints no text, is named by its label, shows the
 * same label as its title on hover and has the common square (`icon-action`). The name is read where a screen reader
 * hears it: Ionic moves `aria-label` from its host to the native button (or link) inside.
 */
export function iconAction(el: Element | null | undefined): { text: string | null; name: string | null; title: string | null; square: boolean } {
  return {
    text: el?.textContent?.trim() ?? null,
    name: el?.shadowRoot?.querySelector('button, a, [role]')?.getAttribute('aria-label') ?? el?.getAttribute('aria-label') ?? null,
    title: el?.getAttribute('title') ?? null,
    square: el?.classList.contains('icon-action') ?? false,
  };
}

/** The `iconAction` of a button that is only its icon, labelled `label`. */
export const iconOnly = (label: string) => ({ text: '', name: label, title: label, square: true });
