// How a session's device and browser read on Account → Security (mockups `account.html`, Active sessions): the
// server sends a code (`accounts/devices.py`, `describe`) and the panel names it in the reader's language
// («Mac (macOS)», «PC con Windows»), the browser as a proper noun with its version, and the ERPlora app as
// «App ERPlora 4.0». A code the panel does not know reads «Unknown device», never blank nor raw.
import type { SessionRowOut } from '../../frontend/sdk-types';

type Translate = (key: string, params?: Record<string, unknown>) => string;

/** The device codes of `accounts/devices.py`, each with its name in the catalogue. */
const DEVICES = new Set(['iphone', 'ipad', 'android', 'windows', 'chromeos', 'mac', 'linux']);
/** Phones and tablets: the card of their row shows a phone. */
const HANDHELD = new Set(['iphone', 'ipad', 'android']);

export function deviceName(t: Translate, code: string): string {
  return t(`accounts.account.sessions.devices.${DEVICES.has(code) ? code : 'unknown'}`);
}

/** The session runs inside the ERPlora app (desktop or Android): closing it may stop a till. */
export function isAppSession(row: Pick<SessionRowOut, 'app_version'>): boolean {
  return row.app_version !== null;
}

export function browserName(t: Translate, row: Pick<SessionRowOut, 'browser' | 'browser_version' | 'app_version'>): string {
  if (isAppSession(row)) return t('accounts.account.sessions.app', { version: row.app_version });
  if (!row.browser) return t('accounts.account.sessions.unknownBrowser');
  return row.browser_version ? `${row.browser} ${row.browser_version}` : row.browser;
}

export function deviceIcon(code: string): string {
  return HANDHELD.has(code) ? 'ion:phone-portrait-outline' : 'ion:laptop-outline';
}
