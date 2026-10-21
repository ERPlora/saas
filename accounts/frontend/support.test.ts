// The SPA's support address (PUBLIC-F18): the one the SaaS embeds next to `spa-config` (`support-email`, base/spa.py,
// from `SUPPORT_EMAIL`), never a second one typed in a page.
import { afterEach, describe, expect, it } from 'vitest';

import { SUPPORT_EMAIL_ID, supportMailto } from './support';

function embed(json: string): void {
  const script = document.createElement('script');
  script.type = 'application/json';
  script.id = SUPPORT_EMAIL_ID;
  script.textContent = json;
  document.body.append(script);
}

afterEach(() => {
  document.getElementById(SUPPORT_EMAIL_ID)?.remove();
});

describe('supportMailto', () => {
  it('writes to the address the SaaS embedded', () => {
    embed('"help@erplora.test"');

    expect(supportMailto()).toBe('mailto:help@erplora.test');
  });

  it.each(['', '""', '42', 'null', 'not json'])('has none to offer when the page carries no valid address (%s)', (json) => {
    embed(json);

    expect(supportMailto()).toBeUndefined();
  });

  it('has none to offer without the block', () => {
    expect(supportMailto()).toBeUndefined();
  });
});
