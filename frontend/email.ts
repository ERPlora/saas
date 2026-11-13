// Whether what was typed looks like an email address: a form's button waits for one instead of
// sending an empty or half-typed address. Only the shape; the server decides whether it is valid.

/** One «@» with something before it and a domain with a dot after it, no spaces; trimmed first. */
const SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function looksLikeEmail(typed: string): boolean {
  return SHAPE.test(typed.trim());
}
