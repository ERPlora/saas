// reCAPTCHA on allauth.headless's public doors (accounts/bot_check.py; Ioan, 2026-10-22): the sign-in, the sign-up,
// «Forgot your password?» and its link, the mailed codes («Send another code» too) and the authenticator app's code.
// Every POST to one of them carries `recaptcha_token`, Google's token of that door's action (frontend/recaptcha.ts),
// added by the allauth client's own `fetch`: the pages create their client with `createProtectedAllauthClient` and
// change nothing else. The server refuses a POST without it in allauth's envelope (400 `recaptcha_failed`, one
// message for the whole form), which the pages already paint. The site key is the page's
// (`spa-config.recaptchaSiteKey`, base/spa.py); empty, reCAPTCHA is off and nothing is added.
import { type AllauthClient, type AllauthDeps, createAllauthClient, type SpaConfig } from '@erplora/ui/sdk';

import { type RecaptchaEnv, recaptchaToken, TOKEN_FIELD } from '../../frontend/recaptcha';

const BROWSER = '/_allauth/browser/v1';

/** The doors and the action of each one's token: the same as `RECAPTCHA_DOORS` of accounts/bot_check.py
 *  (accounts/tests/test_bot_check.py reads this file). */
export const RECAPTCHA_DOORS: Readonly<Record<string, string>> = {
  [`${BROWSER}/auth/login`]: 'login',
  [`${BROWSER}/auth/signup`]: 'signup',
  [`${BROWSER}/auth/password/request`]: 'password_reset',
  [`${BROWSER}/auth/password/reset`]: 'password_reset_confirm',
  [`${BROWSER}/auth/email/verify`]: 'verify_email',
  [`${BROWSER}/auth/email/verify/resend`]: 'verify_email_resend',
  [`${BROWSER}/auth/code/confirm`]: 'login_code',
  [`${BROWSER}/auth/2fa/authenticate`]: 'mfa_authenticate',
};

/** reCAPTCHA's site key the server put in the page (`spa-config.recaptchaSiteKey`); empty when it is off. */
export function recaptchaSiteKey(doc: Document = document): string {
  try {
    const raw = JSON.parse(doc.getElementById('spa-config')?.textContent ?? '{}') as { recaptchaSiteKey?: unknown };
    return typeof raw.recaptchaSiteKey === 'string' ? raw.recaptchaSiteKey : '';
  } catch {
    return '';
  }
}

type FetchImpl = AllauthDeps['fetchImpl'];

/** `fetchImpl` with Google's token in the JSON body of every POST to a door; without a site key, `fetchImpl` as is. */
export function withRecaptcha(fetchImpl: FetchImpl, siteKey: string, env: RecaptchaEnv = {}): FetchImpl {
  if (!siteKey) return fetchImpl;
  return async (url, init) => {
    const action = RECAPTCHA_DOORS[url];
    if (!action || (init.method ?? 'GET').toUpperCase() !== 'POST') return fetchImpl(url, init);
    const token = await recaptchaToken(siteKey, action, env);
    const body = typeof init.body === 'string' && init.body ? (JSON.parse(init.body) as Record<string, unknown>) : {};
    return fetchImpl(url, {
      ...init,
      headers: { ...(init.headers as Record<string, string> | undefined), 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, [TOKEN_FIELD]: token ?? '' }),
    });
  };
}

type AllauthConfig = Pick<SpaConfig, 'csrfCookieName' | 'csrfHeader' | 'deviceIdStorageKey'>;

/** allauth's browser client whose POSTs to the doors carry reCAPTCHA's token (the page's site key by default). */
export function createProtectedAllauthClient(
  config: AllauthConfig,
  { siteKey = recaptchaSiteKey(), env }: { siteKey?: string; env?: RecaptchaEnv } = {},
): AllauthClient {
  return createAllauthClient(config, {
    fetchImpl: withRecaptcha((url, init) => globalThis.fetch(url, init), siteKey, env),
  });
}
