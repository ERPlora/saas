// `next` of the account pages: where to go after signing in, only ever a path of this site.
import { describe, expect, it } from 'vitest';

import { localNext } from './next';

describe('localNext', () => {
  it.each(['/launch', '/hub-login/?hub=a&next=/sales', '/'])('keeps a path of this site (%s)', (path) => {
    expect(localNext(path)).toBe(path);
  });

  it.each(['https://evil.example.com/', '//evil.example.com', '/\\evil.example.com', 'javascript:alert(1)', '', 'launch'])(
    'drops anything that leaves the site or is no path (%s)',
    (value) => {
      expect(localNext(value)).toBeUndefined();
    },
  );

  it('keeps the query and the fragment of a path of this site', () => {
    expect(localNext('/hub-login/?hub=a#x')).toBe('/hub-login/?hub=a#x');
  });

  // The browser strips tabs and newlines from a URL before resolving it (WHATWG), so `/<TAB>/host`
  // reached `location.assign` as `//host`: another site (`?next=/%09/evil.example.com`).
  it.each(['/\t/evil.example.com', '/\n/evil.example.com', '/\r/evil.example.com', '/\u0000/evil.example.com', '/a\u007F'])(
    'drops a path with a control character (%j)',
    (value) => {
      expect(localNext(value)).toBeUndefined();
    },
  );

  it('keeps an escaped tab as what it is: a path of this site', () => {
    expect(localNext('/%09/evil.example.com')).toBe('/%09/evil.example.com');
  });

  it('never hands back a path that normalises into another host (/.//host)', () => {
    expect(localNext('/.//evil.example.com')).toBeUndefined();
  });

  it('drops what a query can carry that is not one string', () => {
    expect(localNext(undefined)).toBeUndefined();
    expect(localNext(null)).toBeUndefined();
    expect(localNext(['/a', '/b'])).toBeUndefined();
  });
});
