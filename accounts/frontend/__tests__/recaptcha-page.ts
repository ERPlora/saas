// Test helper of the sign-in's pages with reCAPTCHA on (accounts/frontend/recaptcha.ts): the page's site key in
// `spa-config` (as base/spa.py writes it) and Google's `grecaptcha` already loaded, answering `token-for-<action>`.
// `forgetRecaptcha` in an `afterEach` undoes both (the stubbed global goes with `vi.unstubAllGlobals`).
import { vi } from 'vitest';

import { resetRecaptcha } from '../../../frontend/recaptcha';

export const SITE_KEY = 'site-key';

export function withRecaptcha() {
  const config = document.createElement('script');
  config.id = 'spa-config';
  config.type = 'application/json';
  config.textContent = JSON.stringify({ recaptchaSiteKey: SITE_KEY });
  document.body.append(config);
  const execute = vi.fn(async (_key: string, { action }: { action: string }) => `token-for-${action}`);
  vi.stubGlobal('grecaptcha', { enterprise: { ready: (callback: () => void) => callback(), execute } });
  return execute;
}

export function forgetRecaptcha(): void {
  resetRecaptcha();
  document.getElementById('spa-config')?.remove();
}
