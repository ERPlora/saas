// The mails the panel's Django sends (file backend, project.ts), read with `@erplora/ui/testing/mail`, shared with
// the Hub's e2e: the newest matching mail to the address written from `since` on (a `Date.now()` taken before the
// action that sends it), so an earlier run's or an earlier test's code to the same address is never read.
import { resolve } from 'node:path';

import { readMailCode, readPasswordResetLink, waitForMail as waitForMailIn } from '@erplora/ui/testing/mail';
import type { Page } from '@playwright/test';

import { djangoPrintWarm, SAAS_DIR } from './django';
import { PANEL_MAIL_DIR } from './project';

/** What a Django process needs for what it mails to land in the panel's mail folder, as the panel's server does. */
export const MAILING: Readonly<Record<string, string>> = {
  EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
  EMAIL_FILE_PATH: PANEL_MAIL_DIR,
};

/** The logo of the branded mails, and the SaaS's file it is. */
export const MAIL_LOGO_URL = 'https://erplora.com/static/public/img/logo.png';
const MAIL_LOGO_FILE = resolve(SAAS_DIR, 'public', 'static', 'public', 'img', 'logo.png');

/**
 * From here on `page` fetches nothing but the mails' logo, served from its file, and writes down every address it
 * asks for (the list returned): a mail painted with `setContent` asks for the logo and nothing else.
 */
export async function onlyTheMailLogo(page: Page): Promise<string[]> {
  const fetched: string[] = [];
  await page.route('**/*', (route) => {
    fetched.push(route.request().url());
    return route.abort();
  });
  await page.route(MAIL_LOGO_URL, (route) => {
    fetched.push(route.request().url());
    return route.fulfill({ path: MAIL_LOGO_FILE, contentType: 'image/png' });
  });
  return fetched;
}

/** The first group (or the whole match) of `match` in the newest mail to `to` since `since`. */
export async function waitForMail(to: string, since: number, match: RegExp): Promise<string> {
  return waitForMailIn({ dir: PANEL_MAIL_DIR, to, since, match });
}

/**
 * The six digits mailed to `to` from `since` on: the sign-in code of every password sign-in
 * (`ACCOUNT_LOGIN_BY_CODE_FORMAT`) or the one that proves the address of a sign-up
 * (`ACCOUNT_EMAIL_VERIFICATION_BY_CODE_FORMAT`), alone on their line.
 */
export async function waitForMailCode(to: string, since: number): Promise<string> {
  return readMailCode({ dir: PANEL_MAIL_DIR, to, since });
}

/**
 * The password reset link mailed `to` from `since` on: the SPA's `/password/reset/key/<key>` on the panel
 * the request came to (`HEADLESS_FRONTEND_URLS`), as the person clicks it.
 */
export async function waitForPasswordResetLink(to: string, since: number): Promise<string> {
  return readPasswordResetLink({ dir: PANEL_MAIL_DIR, to, since });
}

/** A mail as a mail client reads it (Python's `email`): its type, the types of its parts, its HTML and its text. */
export interface MailParts {
  type: string;
  parts: string[];
  html: string;
  text: string;
}

/**
 * The newest mail to `to` written in the panel's mail folder from `since` on whose subject has `subject`, read from its
 * file as a mail client reads it, by the warm Django's Python (what the person sees, painted with `setContent`).
 */
export async function mailPartsOf(to: string, since: number, subject: string): Promise<MailParts> {
  const read = [
    'import email, json, pathlib',
    'from email import policy',
    `folder, to, since, subject = pathlib.Path(${JSON.stringify(PANEL_MAIL_DIR)}), ${JSON.stringify(to)}, ${since / 1000 - 0.05}, ${JSON.stringify(subject)}`,
    'found = None',
    'for path in sorted((p for p in folder.iterdir() if p.is_file() and p.stat().st_mtime >= since), key=lambda p: p.stat().st_mtime):',
    '    for raw in path.read_text().split("\\n" + "-" * 79 + "\\n")[:-1]:',
    '        message = email.message_from_string(raw, policy=policy.default)',
    '        if to in str(message["To"]) and subject.lower() in str(message["Subject"]).lower():',
    '            found = message',
    'assert found is not None, f"no mail to {to} with {subject!r} in {folder}"',
    'print(json.dumps({"type": found.get_content_type(), "parts": [part.get_content_type() for part in found.iter_parts()],',
    '    "html": found.get_body(preferencelist=("html",)).get_content(), "text": found.get_body(preferencelist=("plain",)).get_content()}))',
  ].join('\n');
  return JSON.parse(await djangoPrintWarm(read)) as MailParts;
}
