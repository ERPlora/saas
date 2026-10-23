// flow: ACCOUNTS-F46
// Every mail of erplora.com leaves branded, as text and as HTML (accounts/WORKBOOK.md, MIGRATION-TASK APP-ACCOUNTS-5).
// Three mails land in the panel's mail folder as the person gets them: the sign-in code, sent by the running panel
// at a real sign-in (whose code the e2e still reads from the text part), a renewal that could not be charged
// (billing) and a returned authorisation (fiscal), sent by their own senders. Each is read back from its file and
// its HTML part painted at the three sizes of the migration (390×844, 834×1112, 1440×900): the logo, every line of
// the text, the footer, in the recipient's language, nothing scrolling sideways, and nothing fetched but the logo,
// which the page takes from this checkout, never from the network. Accounts of this spec: `e2e-acc5m-…`.
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page } from '@playwright/test';

import { djangoEnv } from '../django-env';
import { djangoPrint, expect, settled, shot, sidewaysScroll, signIn, test } from './fixtures';
import { PANEL_MAIL_DIR, PANEL_URL } from './project';

const SAAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const LOGO_URL = 'https://erplora.com/static/public/img/logo.png';
const LOGO_FILE = resolve(SAAS_DIR, 'public', 'static', 'public', 'img', 'logo.png');
const PREFIX = 'e2e-acc5m-';
const PASSWORD = 'Centeno-y-masa-madre-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

const BOOT = 'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings");django.setup()';

/** What `code` prints, run by the SaaS's Django with the panel's mail backend: what it sends lands in the folder. */
function djangoMailing(code: string): string {
  return execFileSync('uv', ['run', 'python', '-c', `${BOOT}\n${code}`], {
    cwd: SAAS_DIR,
    env: {
      ...djangoEnv(true),
      EMAIL_BACKEND: 'django.core.mail.backends.filebased.EmailBackend',
      EMAIL_FILE_PATH: PANEL_MAIL_DIR,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

interface ReadMail {
  type: string;
  parts: string[];
  html: string;
  text: string;
}

/**
 * The newest mail to `to` written from `since` on whose subject has `subject`, read from its file as a mail
 * client reads it (Python's `email`): its type, the types of its parts, its HTML and its text.
 */
function mailOf(to: string, since: number, subject: string): ReadMail {
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
  return JSON.parse(djangoPrint(read)) as ReadMail;
}

function removeAccounts(): void {
  djangoPrint(
    `from django.contrib.auth import get_user_model\nget_user_model().objects.filter(email__startswith="${PREFIX}", email__endswith="@example.com").delete()`,
  );
}

/** An account in `language` with its address proven. */
function createAccount(email: string, language: string): { email: string; password: string } {
  djangoPrint(
    [
      'from allauth.account.models import EmailAddress',
      'from django.contrib.auth import get_user_model',
      `user = get_user_model().objects.create_user(email="${email}", password="${PASSWORD}", language="${language}")`,
      'EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})',
    ].join('\n'),
  );
  return { email, password: PASSWORD };
}

/** The HTML part of `mail` at every size: branded, every line of its text there, its shot. */
async function paint(page: Page, key: string, mail: ReadMail, language: string): Promise<void> {
  expect(mail.type, `${key} is text and HTML`).toBe('multipart/alternative');
  expect(mail.parts, `${key} parts`).toEqual(['text/plain', 'text/html']);
  const fetched: string[] = [];
  await page.route('**/*', (route) => {
    fetched.push(route.request().url());
    return route.abort();
  });
  await page.route(LOGO_URL, (route) => {
    fetched.push(route.request().url());
    return route.fulfill({ path: LOGO_FILE, contentType: 'image/png' });
  });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.setContent(mail.html, { waitUntil: 'load' });
    await settled(page);
    await expect(page.locator('html')).toHaveAttribute('lang', language);
    const logo = page.locator('img[alt="ERPlora"]');
    await expect(logo).toBeVisible();
    expect(await logo.evaluate((image: HTMLImageElement) => image.naturalWidth), `${key} logo at ${size.name}`).toBeGreaterThan(0);
    const shown = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
    for (const line of mail.text.split('\n')) {
      const words = line.replace(/^- /, '').replace(/\s+/g, ' ').trim();
      if (words) expect(shown, `${key} at ${size.name} shows «${words}»`).toContain(words);
    }
    expect(await sidewaysScroll(page), `${key} scrolls sideways at ${size.name}`).toEqual([]);
    await page.screenshot({ path: shot(`APP-ACCOUNTS-5-ACCOUNTS-F46-${key}-${size.name}`), fullPage: true });
  }
  expect([...new Set(fetched)], `${key} fetches only the logo`).toEqual([LOGO_URL]);
  await page.unrouteAll();
}

test.describe('ACCOUNTS-F46 the mails of erplora.com, branded, as text and as HTML', () => {
  test.beforeEach(removeAccounts);
  test.afterEach(removeAccounts);

  test('the sign-in code, a charge that failed and a returned authorisation, at the three sizes', async ({ browser }) => {
    const ana = createAccount(`${PREFIX}ana@example.com`, 'en');
    const context = await browser.newContext({ baseURL: PANEL_URL });
    const since = Date.now();
    // The running panel mails the code of a real sign-in; signIn reads it from the text part, as every spec does.
    await signIn(context.request, ana);
    await context.close();
    const signInCode = mailOf(ana.email, since, 'sign-in code');

    const owner = `${PREFIX}owner@example.com`;
    djangoMailing(
      [
        'import uuid',
        'from datetime import date',
        'from decimal import Decimal',
        'from types import SimpleNamespace',
        'from billing import emails as billing',
        'from fiscal import emails as fiscal',
        'hub = SimpleNamespace(id=uuid.UUID("0199a0c4-7f3e-7000-8000-00000000f046"), name="Panadería Ana")',
        `billing.send_payment_failed(hub, to="${owner}", language="es", amount=Decimal("29.99"), declined=True, suspends_on=date(2026, 11, 1))`,
        // The step's own mail, as fiscal.services sends it after the COMMIT of «Return».
        'grant = SimpleNamespace(pk=uuid.UUID("0199a0c4-7f3e-7000-8000-00000000f047"), hub=hub, hub_id=hub.id, version=2, status="returned", reason="La firma del Anexo I no se lee: súbelo escaneado de nuevo, por favor.")',
        `fiscal._tell_the_business(grant, SimpleNamespace(language="es", email="${owner}"))`,
      ].join('\n'),
    );
    const charge = mailOf(owner, since, 'No hemos podido cobrar');
    const fiscal = mailOf(owner, since, 'devuelto la autorización');

    const page = await browser.newPage();
    await paint(page, 'sign-in-code', signInCode, 'en');
    await expect(page.locator('p', { hasText: /^\d{6}$/ })).toBeVisible();
    await paint(page, 'payment-failed', charge, 'es');
    await paint(page, 'authorisation-returned', fiscal, 'es');
    await page.close();
  });
});
