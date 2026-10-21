// The legal texts the sign-in links (PUBLIC-F26): on the web, the page as it is; inside the installed app (or on
// the account surface it opens in the browser), the page in app mode, which the public web keeps for the session.
import { describe, expect, it } from 'vitest';

import { legalHref } from './legal';

describe('legalHref', () => {
  it('links the public page of the same site on the web', () => {
    expect(legalHref('terms', 'web')).toBe('/legal/terms/');
    expect(legalHref('privacy', 'web')).toBe('/legal/privacy/');
  });

  it.each(['desktop', 'mobile', 'account'] as const)('opens it in app mode from the %s surface', (surface) => {
    expect(legalHref('terms', surface)).toBe(`/legal/terms/?surface=${surface}`);
    expect(legalHref('privacy', surface)).toBe(`/legal/privacy/?surface=${surface}`);
  });
});
