// The account pages' UI texts: English source + Spanish (PLAN §5), kept by hand next to the pages
// until Django's catalogues are exported to JSON (as the demo of hub-next does). The texts of a page
// ported from a template keep that template's EXACT msgids, and their Spanish is the msgstr of
// `saas-next/locale/es/LC_MESSAGES/django.po`, so the export finds them already translated. Only
// what the Vue page adds is new, and listed here. A msgid's `%(name)s` is written `{name}` here
// (vue-i18n's named interpolation), and a plural (`msgid` + `msgid_plural`) is vue-i18n's
// `singular | plural`: the same message, in the other syntax.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from './en.json';
import es from './es.json';

type Catalogue = { [key: string]: string | Catalogue };

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(HERE, '..');
const DJANGO_PO = join(HERE, '..', '..', '..', 'locale', 'es', 'LC_MESSAGES', 'django.po');

/** Keys of texts that no template had (a page that talks to the API can fail to reach it). */
const NEW_IN_THE_VUE_PAGES = new Set([
  'accounts.login.failed',
  // allauth answers a 429 without a message (the sign-up's limit, «Send a new code», the reset link).
  'accounts.login.tooManyAttempts',
  'accounts.launch.retry',
  'accounts.twoFactor.loadError',
  // allauth's own alternatives («Use your password», «Use authenticator app or code»), worded as ours.
  'accounts.reauthenticate.useAuthenticator',
  'accounts.reauthenticate.usePassword',
  // The refused «connect» of Google had only a Django message (its msgid is the page's message), no heading.
  'accounts.loginError.googleLinkRefused.heading',
  // The code mailed at every password sign-in (2026-10-15) is new: its expiry sends the visitor back here.
  'accounts.login.codeExpired',
  // The tabs «Sign in» and «Create account» of the launcher (FIX-LAUNCH-TABS): the template had one form.
  'accounts.login.tabsLabel',
  'accounts.login.signIn',
  'accounts.login.signUp',
  'accounts.login.introSignIn',
  'accounts.login.introSignUp',
  'accounts.login.firstTime',
  'accounts.login.createYourAccount',
  'accounts.login.haveAccount',
  'accounts.login.signInInstead',
  'accounts.login.signUpFailed',
  // «Trust this browser for 14 days» (ACCOUNTS-F05) and the trusted browsers (ACCOUNTS-F17): allauth's `mfa/trust.html`
  // asked on a page of its own; here it is a box under the code, and the browsers have their section.
  'accounts.twoFactor.trust',
  'accounts.twoFactor.trustHint',
  'accounts.twoFactor.trustLead',
  // Turning the app off leaves the code mailed at every sign-in (2026-10-15), not «your password only» (ACCOUNTS-F16).
  'accounts.twoFactor.deactivate.lead',
  // The staff the admin keeps out without the app land on /2fa to set it up (ACCOUNTS-F20).
  'accounts.twoFactor.requiredToContinue',
  'accounts.twoFactor.trusted.title',
  'accounts.twoFactor.trusted.lead',
  'accounts.twoFactor.trusted.thisUntil',
  'accounts.twoFactor.trusted.thisNot',
  'accounts.twoFactor.trusted.unknown',
  'accounts.twoFactor.trusted.revoke',
  'accounts.twoFactor.trusted.revoked',
]);

/**
 * The Account page (`/account/:tab`, plan 2026-10-13 L3-B) had no template: its texts, under `accounts.account`, are
 * new. One that happens to be a msgid of django.po («API keys») is translated as django.po translates it, its
 * first letter capitalised as the page needs (django.po writes «claves de API» for the middle of a sentence).
 */
const ACCOUNT_PAGE = 'accounts.account.';

/**
 * Pages whose templates ERPlora/saas had and saas-next never ported (the sign-up's code,
 * `account/confirm_email_verification_code.html`; the password reset, `account/password_reset*.html`):
 * their texts keep those templates' msgids, translated as ERPlora/saas's django.po did, and are new to
 * saas-next's django.po. One that it does have is translated as it translates it, as on the Account page.
 */
const UNPORTED_TEMPLATE_PAGES = ['accounts.verifyEmail.', 'accounts.passwordReset.'];
const newPage = (key: string) => key.startsWith(ACCOUNT_PAGE) || UNPORTED_TEMPLATE_PAGES.some((page) => key.startsWith(page));

/** vue-i18n's separator of plural forms (`singular | plural`). */
const PLURAL = ' | ';

/** vue-i18n's `{name}` → gettext's `%(name)s`. */
const asGettext = (message: string) => message.replace(/\{(\w+)\}/g, '%($1)s');

function flatten(catalogue: Catalogue, prefix = ''): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

/**
 * `{msgid: msgstr}` of a .po file (single and multi-line strings; obsolete entries skipped). A
 * plural entry is keyed `msgid | msgid_plural` with `msgstr[0] | msgstr[1]`, as vue-i18n writes it.
 */
function readPo(path: string): Map<string, string> {
  const entries = new Map<string, string>();
  const unquote = (line: string) => JSON.parse(line.slice(line.indexOf('"'))) as string;
  let parts: Record<string, string> = {};
  let current: string | null = null;
  const flush = () => {
    const { msgid, msgid_plural: plural, msgstr } = parts;
    if (msgid && plural !== undefined) {
      const forms = Object.keys(parts)
        .filter((key) => key.startsWith('msgstr['))
        .sort()
        .map((key) => parts[key]);
      entries.set(`${msgid}${PLURAL}${plural}`, forms.join(PLURAL));
    } else if (msgid && msgstr !== undefined) {
      entries.set(msgid, msgstr);
    }
    parts = {};
    current = null;
  };
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    const start = /^(msgid_plural|msgid|msgstr(?:\[\d\])?) "/.exec(line);
    if (start) {
      if (start[1] === 'msgid') flush();
      current = start[1];
      parts[current] = unquote(line);
    } else if (line.startsWith('"') && current) {
      parts[current] += unquote(line);
    } else if (!line.trim()) {
      flush();
    }
  }
  flush();
  return entries;
}

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return vueFiles(path);
    return entry.name.endsWith('.vue') ? [path] : [];
  });
}

const EN = flatten(en as Catalogue);
const ES = flatten(es as Catalogue);
const PO = readPo(DJANGO_PO);

describe('accounts catalogues (en source + es)', () => {
  it('live under the app prefix, so merging them into the shell never collides', () => {
    expect(Object.keys(en)).toEqual(['accounts']);
    expect(Object.keys(es)).toEqual(['accounts']);
  });

  it('have exactly the same keys', () => {
    expect([...ES.keys()].sort()).toEqual([...EN.keys()].sort());
  });

  it('have no empty message', () => {
    for (const [key, message] of [...EN, ...ES]) expect(message.trim(), key).not.toBe('');
  });

  it("keep the template's exact msgids, translated as django.po translates them", () => {
    expect(PO.size).toBeGreaterThan(0);
    for (const [key, message] of EN) {
      if (NEW_IN_THE_VUE_PAGES.has(key) || newPage(key)) continue;
      const msgid = asGettext(message);
      expect(PO.has(msgid), `${key}: "${msgid}" is not a msgid of django.po`).toBe(true);
      expect(asGettext(ES.get(key)!), key).toBe(PO.get(msgid));
    }
  });

  it('translate a new page text that django.po already has as django.po does', () => {
    const page = [...EN].filter(([key]) => newPage(key));
    expect(page.length).toBeGreaterThan(0);
    for (const prefix of UNPORTED_TEMPLATE_PAGES) expect(page.some(([key]) => key.startsWith(prefix)), prefix).toBe(true);
    for (const [key, message] of page) {
      const msgid = asGettext(message);
      const capital = (message: string) => message.charAt(0).toLocaleUpperCase('es') + message.slice(1);
      if (PO.has(msgid) && PO.get(msgid)) expect(capital(asGettext(ES.get(key)!)), key).toBe(capital(PO.get(msgid)!));
    }
  });

  it('list as new only texts that really are new', () => {
    for (const key of NEW_IN_THE_VUE_PAGES) {
      expect(EN.has(key), key).toBe(true);
      expect(PO.has(asGettext(EN.get(key)!)), key).toBe(false);
    }
  });

  it('write a plural with as many forms in both languages', () => {
    const forms = (message: string) => message.split(PLURAL).length;
    for (const [key, message] of EN) expect(forms(ES.get(key)!), key).toBe(forms(message));
  });

  it('write a placeholder the same in both languages', () => {
    const placeholders = (message: string) => [...message.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    for (const [key, message] of EN) expect(placeholders(ES.get(key)!), key).toEqual(placeholders(message));
  });

  it('cover every key the account pages use', () => {
    const files = vueFiles(FRONTEND);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const [, key] of source.matchAll(/\bt\(\s*'([^']+)'/g)) expect(EN.has(key), `${file}: ${key}`).toBe(true);
    }
  });
});
