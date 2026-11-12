// What the session says of the account changed: its language (Account → Preferences) or its name (Account →
// Profile). The entry point (`main.ts`) owns the session the shell paints, so a page says it on the window and the
// entry reads `base.session.me` again: the side menu the server translates, and the person at its top, follow
// without a reload (saas#292). The Hub does the same with its own event.

/** Dispatched on the window when what the session says of the account changed. */
export const SESSION_CHANGED = 'erplora:saas-session-changed';

export function sessionChanged(target: EventTarget = window): void {
  target.dispatchEvent(new Event(SESSION_CHANGED));
}

/** Listens for `sessionChanged`; returns the function that stops listening. */
export function onSessionChanged(listener: () => void, target: EventTarget = window): () => void {
  target.addEventListener(SESSION_CHANGED, listener);
  return () => target.removeEventListener(SESSION_CHANGED, listener);
}
