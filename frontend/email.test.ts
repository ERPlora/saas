// Whether what was typed looks like an email address, before a form sends it (audit 2 R-28, R-32): only the
// shape — one «@», something before it, a domain with a dot after it, no spaces — so a button waits for an address;
// the server still decides whether it is valid and says why on the field.
import { describe, expect, it } from 'vitest';

import { looksLikeEmail } from './email';

describe('looksLikeEmail', () => {
  it('takes an address, with the spaces around it trimmed', () => {
    expect(looksLikeEmail('jorge@example.com')).toBe(true);
    expect(looksLikeEmail('  ana.lópez+bar@sub.example.es ')).toBe(true);
  });

  it('refuses what is empty, half-typed or not one address', () => {
    for (const typed of ['', '   ', 'nope', 'jorge@', '@example.com', 'jorge@example', 'jo rge@example.com', 'a@b@example.com']) {
      expect(looksLikeEmail(typed), typed).toBe(false);
    }
  });
});
