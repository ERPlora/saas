// reCAPTCHA Enterprise in the e2e. The public server is production-like (DEBUG off), so reCAPTCHA is off there, as
// in production since 2026-10-23 (Ioan: the WAF on the ALB, the attempt limits), unless the run asks for it with
// `E2E_RECAPTCHA=1` (`recaptchaOn`): then it asks the double of recaptcha-double.ts for its assessments
// (`RECAPTCHA_ENDPOINT`), with an API key that is not Google's, and its pages get a fake enterprise.js
// (`fakeGoogleRecaptcha`) whose tokens the double reads (`e2e-human:<action>`, `e2e-bot:<action>`). The fake works as Google's does where the page's
// policies are concerned: our code inserts www.google.com/recaptcha/enterprise.js, which inserts its release from
// www.gstatic.com by a plain string with the page's nonce, and the release creates the `goog#html` Trusted Types
// policy and paints the badge. So a CSP or a Trusted Types policy that would block Google blocks the fake too.
// The panel's servers run with reCAPTCHA off (panel/project.ts): their specs sign in through the API.
//
// The site key the public server hands its pages is the checkout's own (`.env`, localhost) when there is one, so
// recaptcha.spec.ts can also load Google's real script on `localhost` (its token is checked against nothing).
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { BrowserContext } from '@playwright/test';

import type { Stack } from './stack.ts';

/** The site key of a run without one in `.env`: no Google script accepts it, the fake ignores it. */
export const E2E_RECAPTCHA_SITE_KEY = 'e2e-recaptcha-site-key';
/** The API key the public server sends the double: never the real one of `.env`. */
export const E2E_RECAPTCHA_API_KEY = 'e2e-recaptcha-api-key';
/** Where the fake loader takes its release from: Google's static origin, as the real one. */
export const FAKE_RELEASE_URL = 'https://www.gstatic.com/recaptcha/releases/e2e/recaptcha__en.js';

type Env = Record<string, string | undefined>;

/** A variable as Django reads it: the environment first, then the checkout's `.env`; empty without one. */
function localSetting(name: string, saasDir: string, env: Env): string {
  if (env[name]) return env[name];
  const file = join(saasDir, '.env');
  if (!existsSync(file)) return '';
  const pattern = new RegExp(`^\\s*${name}\\s*=`);
  const line = readFileSync(file, 'utf8')
    .split('\n')
    .find((entry) => pattern.test(entry));
  return line ? line.slice(line.indexOf('=') + 1).trim() : '';
}

/** RECAPTCHA_SITE_KEY of this checkout (the localhost key, public). */
export function localRecaptchaSiteKey(saasDir: string, env: Env = process.env): string {
  return localSetting('RECAPTCHA_SITE_KEY', saasDir, env);
}

/** RECAPTCHA_API_KEY of this checkout: secret, only ever sent to Google (`assessWithGoogle`), never printed. */
export function localRecaptchaApiKey(saasDir: string, env: Env = process.env): string {
  return localSetting('RECAPTCHA_API_KEY', saasDir, env);
}

/** Google's own verdict on a token, as live.recaptcha asks it (the spec with Google's real script, when the
 *  checkout has its API key). */
export async function assessWithGoogle({
  token,
  action,
  siteKey,
  apiKey,
  fetchImpl = (url, init) => fetch(url, init),
}: {
  token: string;
  action: string;
  siteKey: string;
  apiKey: string;
  fetchImpl?: (url: string, init: RequestInit) => Promise<Response>;
}): Promise<{ valid: boolean; action?: string; score?: number; invalidReason?: string }> {
  const answer = await fetchImpl(
    `https://recaptchaenterprise.googleapis.com/v1/projects/erplora/assessments?key=${encodeURIComponent(apiKey)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: { token, siteKey, expectedAction: action } }),
    },
  );
  const body = (await answer.json()) as {
    tokenProperties?: { valid?: boolean; action?: string; invalidReason?: string };
    riskAnalysis?: { score?: number };
  };
  return {
    valid: body.tokenProperties?.valid === true,
    action: body.tokenProperties?.action,
    score: body.riskAnalysis?.score,
    invalidReason: body.tokenProperties?.invalidReason,
  };
}

/** Whether the run switches reCAPTCHA on in the public server (`E2E_RECAPTCHA=1`); off by default, as production. */
export function recaptchaOn(env: Env = process.env): boolean {
  return env.E2E_RECAPTCHA === '1';
}

/** The public server's reCAPTCHA: off by default (whatever `.env` says), as production; with `E2E_RECAPTCHA=1`, on,
 *  with the double of `stack` for the assessments and the local site key when there is one. */
export function recaptchaServerEnv(stack: Pick<Stack, 'recaptchaDoublePort'>, saasDir: string, env: Env = process.env): Record<string, string> {
  if (!recaptchaOn(env)) return { RECAPTCHA_ENABLED: 'False' };
  return {
    RECAPTCHA_ENABLED: 'True',
    RECAPTCHA_SITE_KEY: localRecaptchaSiteKey(saasDir, env) || E2E_RECAPTCHA_SITE_KEY,
    RECAPTCHA_API_KEY: E2E_RECAPTCHA_API_KEY,
    RECAPTCHA_ENDPOINT: `http://127.0.0.1:${stack.recaptchaDoublePort}/v1/projects/erplora/assessments`,
  };
}

/** The fake enterprise.js: `grecaptcha.enterprise.ready` queues until its release loads, which it inserts as Google's
 *  loader does (a string `src` on www.gstatic.com, the page's nonce). */
export function fakeLoader(): string {
  return `(function () {
  var g = window.grecaptcha = window.grecaptcha || {};
  var e = g.enterprise = g.enterprise || {};
  var queue = window.__e2eRecaptchaReady = window.__e2eRecaptchaReady || [];
  e.ready = function (callback) { queue.push(callback); };
  var script = document.createElement('script');
  var nonced = document.querySelector('script[nonce]');
  var nonce = nonced && (nonced.nonce || nonced.getAttribute('nonce'));
  if (nonce) script.setAttribute('nonce', nonce);
  script.src = ${JSON.stringify(FAKE_RELEASE_URL)};
  document.head.appendChild(script);
})();`;
}

/** The fake release: Google's `goog#html` policy, the badge, and `execute` answering `e2e-<kind>:<action>`. */
export function fakeRelease(kind: 'human' | 'bot'): string {
  return `(function () {
  if (window.trustedTypes && window.trustedTypes.createPolicy) {
    window.trustedTypes.createPolicy('goog#html', {
      createHTML: function (s) { return s; },
      createScript: function (s) { return s; },
      createScriptURL: function (s) { return s; }
    });
  }
  var badge = document.createElement('div');
  badge.className = 'grecaptcha-badge';
  badge.textContent = 'reCAPTCHA';
  document.body.appendChild(badge);
  var e = window.grecaptcha.enterprise;
  e.execute = function (key, options) { return Promise.resolve(${JSON.stringify(`e2e-${kind}:`)} + options.action); };
  e.ready = function (callback) { callback(); };
  var queue = window.__e2eRecaptchaReady || [];
  window.__e2eRecaptchaReady = [];
  queue.forEach(function (callback) { callback(); });
})();`;
}

/**
 * Google's reCAPTCHA in `context`, played: a person's tokens by default, a bot's, or Google unreachable (`blocked`,
 * an extension that blocks it: no token at all).
 */
export async function fakeGoogleRecaptcha(context: BrowserContext, kind: 'human' | 'bot' | 'blocked' = 'human'): Promise<void> {
  await context.unrouteAll({ behavior: 'ignoreErrors' });
  await context.route('https://www.google.com/recaptcha/**', (route) =>
    kind === 'blocked' ? route.abort('blockedbyclient') : route.fulfill({ contentType: 'text/javascript', body: fakeLoader() }),
  );
  await context.route('https://www.gstatic.com/recaptcha/**', (route) =>
    kind === 'blocked' ? route.abort('blockedbyclient') : route.fulfill({ contentType: 'text/javascript', body: fakeRelease(kind) }),
  );
}

/** What the double was asked so far (`{token, expectedAction}`), oldest first. */
export async function askedAssessments(stack: Pick<Stack, 'recaptchaDoublePort'>): Promise<Array<{ token: string; expectedAction: string }>> {
  const answer = await fetch(`http://127.0.0.1:${stack.recaptchaDoublePort}/assessments`);
  return (await answer.json()) as Array<{ token: string; expectedAction: string }>;
}
