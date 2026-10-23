// @vitest-environment node
// reCAPTCHA in the e2e (recaptcha.ts): the public server's settings (the double of recaptcha-double.ts for the
// assessments, the local site key of `.env` when there is one) and the fake enterprise.js its pages get.
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  assessWithGoogle,
  E2E_RECAPTCHA_API_KEY,
  E2E_RECAPTCHA_SITE_KEY,
  fakeLoader,
  fakeRelease,
  localRecaptchaApiKey,
  localRecaptchaSiteKey,
  recaptchaServerEnv,
} from './recaptcha';
import { stackFrom } from './stack';

const SHARED = stackFrom({});
const OWN = stackFrom({ E2E_SAAS_PORT: '8030' });

function saasDir(dotenv?: string): string {
  const dir = mkdtempSync(join(tmpdir(), 'saas-recaptcha-'));
  if (dotenv !== undefined) writeFileSync(join(dir, '.env'), dotenv);
  return dir;
}

describe('localRecaptchaSiteKey', () => {
  it('reads RECAPTCHA_SITE_KEY of the checkout’s .env', () => {
    expect(localRecaptchaSiteKey(saasDir('DEBUG=True\nRECAPTCHA_SITE_KEY=6Le-local\nRECAPTCHA_API_KEY=secret\n'), {})).toBe('6Le-local');
  });

  it('takes the exported one first, as Django does', () => {
    expect(localRecaptchaSiteKey(saasDir('RECAPTCHA_SITE_KEY=6Le-file\n'), { RECAPTCHA_SITE_KEY: '6Le-env' })).toBe('6Le-env');
  });

  it.each([['no .env', undefined], ['no key', 'DEBUG=True\n'], ['an empty key', 'RECAPTCHA_SITE_KEY=\n'], ['a commented key', '# RECAPTCHA_SITE_KEY=6Le\n']])(
    'is empty with %s',
    (_case, dotenv) => {
      expect(localRecaptchaSiteKey(saasDir(dotenv), {})).toBe('');
    },
  );
});

describe('localRecaptchaApiKey', () => {
  it('reads RECAPTCHA_API_KEY of the checkout’s .env, the environment first', () => {
    expect(localRecaptchaApiKey(saasDir('RECAPTCHA_API_KEY=from-file\n'), {})).toBe('from-file');
    expect(localRecaptchaApiKey(saasDir('RECAPTCHA_API_KEY=from-file\n'), { RECAPTCHA_API_KEY: 'from-env' })).toBe('from-env');
    expect(localRecaptchaApiKey(saasDir(), {})).toBe('');
  });
});

describe('assessWithGoogle', () => {
  it('asks Google’s REST API as live.recaptcha does and reads its verdict', async () => {
    const asked: Array<[string, RequestInit]> = [];
    const fetchImpl = async (url: string, init: RequestInit) => {
      asked.push([url, init]);
      return new Response(JSON.stringify({ tokenProperties: { valid: true, action: 'login' }, riskAnalysis: { score: 0.3 } }));
    };

    const verdict = await assessWithGoogle({ token: 't', action: 'login', siteKey: 'site', apiKey: 'api', fetchImpl });

    expect(verdict).toEqual({ valid: true, action: 'login', score: 0.3, invalidReason: undefined });
    expect(asked[0][0]).toBe('https://recaptchaenterprise.googleapis.com/v1/projects/erplora/assessments?key=api');
    expect(JSON.parse(asked[0][1].body as string)).toEqual({ event: { token: 't', siteKey: 'site', expectedAction: 'login' } });
  });
});

describe('recaptchaServerEnv', () => {
  it('sends the assessments to the double of the stack, with an API key that is not Google’s', () => {
    expect(recaptchaServerEnv(SHARED, saasDir(), {})).toEqual({
      RECAPTCHA_SITE_KEY: E2E_RECAPTCHA_SITE_KEY,
      RECAPTCHA_API_KEY: E2E_RECAPTCHA_API_KEY,
      RECAPTCHA_ENDPOINT: 'http://127.0.0.1:8018/v1/projects/erplora/assessments',
    });
    expect(recaptchaServerEnv(OWN, saasDir(), {}).RECAPTCHA_ENDPOINT).toBe('http://127.0.0.1:8038/v1/projects/erplora/assessments');
  });

  it('keeps the local site key when the checkout has one, for the spec with Google’s real script', () => {
    const env = recaptchaServerEnv(SHARED, saasDir('RECAPTCHA_SITE_KEY=6Le-local\nRECAPTCHA_API_KEY=the-real-secret\n'), {});
    expect(env.RECAPTCHA_SITE_KEY).toBe('6Le-local');
    expect(env.RECAPTCHA_API_KEY).toBe(E2E_RECAPTCHA_API_KEY);
  });
});

describe('the fake enterprise.js', () => {
  type FakeWindow = {
    grecaptcha?: { enterprise: { ready: (callback: () => void) => void; execute?: (key: string, options: { action: string }) => Promise<string> } };
    trustedTypes?: { createPolicy: (name: string, rules: object) => unknown };
    __e2eRecaptchaReady?: Array<() => void>;
  };

  /** Runs the loader, then the release it asks for, in a window of their own. */
  function run(kind: 'human' | 'bot') {
    const inserted: Array<{ src: string; nonce: string | null }> = [];
    const policies: string[] = [];
    const appended: string[] = [];
    const win: FakeWindow = { trustedTypes: { createPolicy: (name) => policies.push(name) } };
    const doc = {
      createElement: (tag: string) => {
        const el = { tag, src: '', className: '', textContent: '', attributes: {} as Record<string, string>, setAttribute(n: string, v: string) { this.attributes[n] = v; } };
        return el;
      },
      querySelector: () => ({ nonce: 'n0nce' }),
      head: { appendChild: (el: { src: string; attributes: Record<string, string> }) => inserted.push({ src: el.src, nonce: el.attributes.nonce ?? null }) },
      body: { appendChild: (el: { className: string }) => appended.push(el.className) },
    };
    new Function('window', 'document', fakeLoader())(win, doc);
    new Function('window', 'document', fakeRelease(kind))(win, doc);
    return { win, inserted, policies, appended };
  }

  it('loads its release from gstatic with the page’s nonce, as Google’s loader does', () => {
    const { inserted } = run('human');
    expect(inserted).toEqual([{ src: 'https://www.gstatic.com/recaptcha/releases/e2e/recaptcha__en.js', nonce: 'n0nce' }]);
  });

  it('creates Google’s Trusted Types policy, paints the badge and gives a token of the action', async () => {
    const { win, policies, appended } = run('human');
    const ready = await new Promise<boolean>((resolve) => win.grecaptcha!.enterprise.ready(() => resolve(true)));

    expect(ready).toBe(true);
    expect(policies).toEqual(['goog#html']);
    expect(appended).toEqual(['grecaptcha-badge']);
    await expect(win.grecaptcha!.enterprise.execute!('k', { action: 'login' })).resolves.toBe('e2e-human:login');
  });

  it('a bot gets a bot’s token', async () => {
    const { win } = run('bot');
    await expect(win.grecaptcha!.enterprise.execute!('k', { action: 'contact' })).resolves.toBe('e2e-bot:contact');
  });
});
