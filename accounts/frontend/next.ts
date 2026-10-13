// `next` of the account pages (`?next=`, Django's parameter): where to go after signing in.

/** Any origin works: only "does it stay on the origin it is resolved against" is asked of it. */
const SITE = 'http://site.invalid';
/** A path that starts `//` or `/\` is another host to the browser. */
const OTHER_HOST = /^\/[/\\]/;
/** The browser drops tabs and newlines from a URL before resolving it, so `/<TAB>/host` is `//host`. */
const CONTROL = /[\u0000-\u001F\u007F]/;

/**
 * `value` resolved as a path of this site (`pathname + search + hash`), else `undefined`: no open
 * redirect. Never a URL nor `//host`/`/\host`, no control character, and the resolved path is
 * checked again (`/.//host` would normalise into `//host`).
 */
export function localNext(value: unknown): string | undefined {
  if (typeof value !== 'string' || !value.startsWith('/') || OTHER_HOST.test(value) || CONTROL.test(value)) return undefined;
  let url: URL;
  try {
    url = new URL(value, SITE);
  } catch {
    return undefined;
  }
  if (url.origin !== SITE) return undefined;
  const path = `${url.pathname}${url.search}${url.hash}`;
  return OTHER_HOST.test(path) ? undefined : path;
}
