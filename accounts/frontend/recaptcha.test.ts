// reCAPTCHA on the sign-in's doors of allauth.headless (accounts/bot_check.py): every POST to one of them carries
// `recaptcha_token`, Google's token of that door's action, added by the allauth client's `fetch`; the pages create
// their client with `createProtectedAllauthClient`. The site key comes from the page (`spa-config.recaptchaSiteKey`,
// base/spa.py); empty, reCAPTCHA is off and nothing is added.
import { ALLAUTH_BROWSER_BASE } from '@erplora/ui/sdk';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { resetRecaptcha } from '../../frontend/recaptcha';
import { anonymous, fakeAllauth, pendingLoginCode } from './__tests__/allauth-server';
import { createProtectedAllauthClient, RECAPTCHA_DOORS, recaptchaSiteKey, withRecaptcha } from './recaptcha';

const CONFIG = { csrfCookieName: 'csrftoken', csrfHeader: 'X-CSRFToken', deviceIdStorageKey: 'erplora.device' };

type Grecaptcha = { enterprise: { ready: (callback: () => void) => void; execute: ReturnType<typeof vi.fn> } };

/** Google's `grecaptcha` already on the page: a token per action. */
function google(execute = vi.fn(async (_key: string, { action }: { action: string }) => `token-for-${action}`)) {
  const grecaptcha: Grecaptcha = { enterprise: { ready: (callback) => callback(), execute } };
  vi.stubGlobal('grecaptcha', grecaptcha);
  return execute;
}

function spaConfig(json: string) {
  const el = document.createElement('script');
  el.id = 'spa-config';
  el.type = 'application/json';
  el.textContent = json;
  document.body.append(el);
}

afterEach(() => {
  resetRecaptcha();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('recaptchaSiteKey', () => {
  it('reads the site key the server put in spa-config', () => {
    spaConfig('{"recaptchaSiteKey": "site-key", "csrfCookieName": "csrftoken"}');
    expect(recaptchaSiteKey(document)).toBe('site-key');
  });

  it.each([
    ['no spa-config', ''],
    ['no key', '{}'],
    ['not a string', '{"recaptchaSiteKey": 42}'],
    ['not JSON', '{'],
  ])('is empty with %s', (_case, json) => {
    if (json) spaConfig(json);
    expect(recaptchaSiteKey(document)).toBe('');
  });
});

describe('withRecaptcha', () => {
  it.each(Object.entries(RECAPTCHA_DOORS))('adds the token of its action to a POST to %s', async (path, action) => {
    const execute = google();
    const inner = vi.fn(async () => new Response('{}'));

    await withRecaptcha(inner, 'site-key')(path, {
      method: 'POST',
      headers: { 'X-CSRFToken': 'tok' },
      body: JSON.stringify({ email: 'a@example.com' }),
    });

    expect(execute).toHaveBeenCalledWith('site-key', { action });
    const [, init] = inner.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ email: 'a@example.com', recaptcha_token: `token-for-${action}` });
    expect(init.headers).toEqual({ 'X-CSRFToken': 'tok', 'Content-Type': 'application/json' });
  });

  it('gives a POST without a body («Send another code») one with the token', async () => {
    google();
    const inner = vi.fn(async () => new Response('{}'));

    await withRecaptcha(inner, 'site-key')(`${ALLAUTH_BROWSER_BASE}/auth/email/verify/resend`, { method: 'POST', headers: {} });

    const [, init] = inner.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ recaptcha_token: 'token-for-verify_email_resend' });
  });

  it.each([
    ['a read of a door', `${ALLAUTH_BROWSER_BASE}/auth/password/reset`, 'GET'],
    ['another door', `${ALLAUTH_BROWSER_BASE}/auth/session`, 'DELETE'],
    ['the account behind a session', `${ALLAUTH_BROWSER_BASE}/account/password/change`, 'POST'],
  ])('leaves %s alone', async (_case, path, method) => {
    const execute = google();
    const inner = vi.fn(async () => new Response('{}'));
    const init = { method, headers: {}, body: method === 'GET' ? undefined : '{"a":1}' };

    await withRecaptcha(inner, 'site-key')(path, init);

    expect(inner).toHaveBeenCalledWith(path, init);
    expect(execute).not.toHaveBeenCalled();
  });

  it('adds nothing when reCAPTCHA is off (no site key)', async () => {
    const execute = google();
    const inner = vi.fn(async () => new Response('{}'));
    const init = { method: 'POST', headers: {}, body: '{"email":"a@example.com"}' };

    await withRecaptcha(inner, '')(`${ALLAUTH_BROWSER_BASE}/auth/login`, init);

    expect(inner).toHaveBeenCalledWith(`${ALLAUTH_BROWSER_BASE}/auth/login`, init);
    expect(execute).not.toHaveBeenCalled();
  });

  it('sends an empty token when Google gives none: the server refuses it and says why', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    google(vi.fn(async () => Promise.reject(new Error('blocked'))));
    const inner = vi.fn(async () => new Response('{}'));

    await withRecaptcha(inner, 'site-key')(`${ALLAUTH_BROWSER_BASE}/auth/login`, { method: 'POST', headers: {}, body: '{}' });

    const [, init] = inner.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ recaptcha_token: '' });
  });
});

describe('createProtectedAllauthClient', () => {
  it('signs in with the token of `login`, through the stubbed fetch', async () => {
    google();
    const { callsTo } = fakeAllauth({ 'POST /auth/login': pendingLoginCode, 'GET /auth/session': anonymous });

    await createProtectedAllauthClient(CONFIG, { siteKey: 'site-key' }).login({ email: 'a@example.com', password: 'pw' });

    expect(callsTo('POST /auth/login')[0].body).toEqual({ email: 'a@example.com', password: 'pw', recaptcha_token: 'token-for-login' });
  });

  it('takes the page’s site key by default', async () => {
    spaConfig('{"recaptchaSiteKey": "page-key"}');
    const execute = google();
    fakeAllauth({ 'POST /auth/password/request': () => new Response('{"status": 200}', { status: 200 }) });

    await createProtectedAllauthClient(CONFIG).requestPasswordReset('a@example.com');

    expect(execute).toHaveBeenCalledWith('page-key', { action: 'password_reset' });
  });
});
