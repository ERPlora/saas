// The legal texts the sign-in links (PUBLIC-F26). They are pages of the public web on this same site; from the
// installed app (or the account surface it opens in the browser) they carry `?surface=`, so the public web shows
// them in app mode: the text and «Back», without its menu, footer or cookie notice (public/context_processors.py).

export type LegalText = 'terms' | 'privacy';

/** The address of a legal text for a visitor on `surface` (`web`, `desktop`, `mobile` or `account`). */
export function legalHref(text: LegalText, surface: string): string {
  const path = `/legal/${text}/`;
  return surface === 'web' ? path : `${path}?surface=${encodeURIComponent(surface)}`;
}
