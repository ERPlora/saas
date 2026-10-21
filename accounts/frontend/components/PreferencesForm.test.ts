// Account → Preferences (mockups `account.html` «preferences»): appearance (system, light, dark: the shell's theme,
// painted at once and kept in the account), language (the account's, which the mails and the jump to a business
// read too) and the mail notices: «Security, invoices and payments» always on, «Business notices» a switch (the
// mail that a business is ready); no «ERPlora news», a mail ERPlora never sends (ACCOUNTS-F23). Each control saves on its own
// (`accounts.preferences.update`, only what changed) and says so; a refusal puts the control back. A failed load
// is said with «Retry», never a skeleton for ever (audit 2026-10-14, R-08).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { setThemeMode, themeMode } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import {
  type ApiCall,
  apiError,
  choose,
  errorFrame,
  flush,
  HELLO,
  ionProps,
  LIVE_TIMEOUT_MS,
  mountPanel,
  preferences,
  subId,
} from '../__tests__/mount-panel';
import type { PreferencesOut } from '../../../frontend/sdk-types';
import PreferencesForm from './PreferencesForm.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  setThemeMode('system');
  document.documentElement.lang = '';
  document.body.innerHTML = '';
});

async function setup(
  now: PreferencesOut = preferences(),
  api: (call: ApiCall) => Response | Promise<Response> = () => Response.json(now),
  locale: 'en' | 'es' = 'en',
) {
  const s = await mountPanel(PreferencesForm, { api, locale });
  const stream = await s.live();
  await s.result(stream, 'accounts.preferences.get', now);
  return { ...s, stream };
}

describe('PreferencesForm', () => {
  it('shows the account’s preferences and paints its theme', async () => {
    const s = await setup(preferences({ theme_mode: 'dark', hub_alerts: true }));
    expect(ionProps(s.q('preferences-theme'), 'value')).toEqual({ value: 'dark' });
    expect(themeMode.value).toBe('dark');
    expect(document.documentElement.classList.contains('ion-palette-dark')).toBe(true);
    expect(ionProps(s.q('preferences-language'), 'value', 'mode', 'fill', 'interface')).toEqual({
      value: 'en',
      mode: 'md',
      fill: 'outline',
      interface: 'popover',
    });
    expect(ionProps(s.q('preferences-invoices'), 'checked', 'disabled')).toEqual({ checked: true, disabled: true });
    expect(ionProps(s.q('preferences-hub-alerts'), 'checked')).toEqual({ checked: true });
    expect(s.q('preferences-marketing')).toBeNull();
  });

  it('says which mails always go and what «Business notices» is (ACCOUNTS-F23)', async () => {
    const s = await setup(preferences());
    expect(s.q('preferences-mails')?.textContent).toContain('Security, invoices and payments');
    expect(s.q('preferences-mails')?.textContent).toContain(
      'Always on: sign-in codes, security notices, invoices, payments and anything that needs you to act.',
    );
    expect(s.q('preferences-mails')?.textContent).toContain('When a business of yours is ready to open.');
    expect(s.q('preferences-mails')?.textContent).not.toContain('News from ERPlora');
  });

  it('says them in Spanish', async () => {
    const s = await setup(preferences(), undefined, 'es');
    expect(s.q('preferences-mails')?.textContent).toContain('Seguridad, facturas y pagos');
    expect(s.q('preferences-mails')?.textContent).toContain('Cuando un negocio tuyo está listo para abrir.');
  });

  it('paints a theme at once and keeps it in the account', async () => {
    const s = await setup(preferences(), () => Response.json(preferences({ theme_mode: 'dark' })));
    await choose(s.q('preferences-theme'), { value: 'dark' });
    expect(document.documentElement.classList.contains('ion-palette-dark')).toBe(true);
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([['/api/accounts/preferences', { theme_mode: 'dark' }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Preferences saved');
  });

  it('puts the theme back when the account refuses it', async () => {
    const s = await setup(preferences({ theme_mode: 'light' }), () => Promise.reject(new TypeError('Failed to fetch')) as never);
    await choose(s.q('preferences-theme'), { value: 'dark' });
    expect(themeMode.value).toBe('light');
    expect(toastError).toHaveBeenCalledWith('We could not reach ERPlora. Check your connection and try again.');
  });

  it('switches the language of the panel with the account’s', async () => {
    const s = await setup(preferences(), () => Response.json(preferences({ language: 'es' })));
    await choose(s.q('preferences-language'), { value: 'es' });
    expect(s.calls().map((c) => c.body)).toEqual([{ language: 'es' }]);
    expect(s.i18n.global.locale.value).toBe('es');
    expect(document.documentElement.lang).toBe('es');
    expect(toastSuccess).toHaveBeenCalledWith('Preferencias guardadas');
  });

  it('saves «Business notices» on its own', async () => {
    const s = await setup(preferences(), () => Response.json(preferences({ hub_alerts: false })));
    await choose(s.q('preferences-hub-alerts'), { checked: false });
    expect(s.calls().map((c) => c.body)).toEqual([{ hub_alerts: false }]);
    expect(toastSuccess).toHaveBeenCalledWith('Preferences saved');
  });

  it('says a refusal of a switch and puts it back', async () => {
    const s = await setup(preferences({ hub_alerts: true }), () => apiError(429, 'rate_limited', 'Too many requests.'));
    await choose(s.q('preferences-hub-alerts'), { checked: false });
    expect(toastError).toHaveBeenCalledWith('Too many requests.');
    expect(ionProps(s.q('preferences-hub-alerts'), 'checked')).toEqual({ checked: true });
  });

  it('shows it is loading, and a failed load with «Retry»', async () => {
    const s = await mountPanel(PreferencesForm);
    const stream = await s.live();
    expect(s.q('preferences-loading')).not.toBeNull();
    stream.push(errorFrame(subId(s.client, 'accounts.preferences.get'), 'server_error'));
    await flush();
    expect(s.q('preferences-error')?.textContent).toContain('We could not load your preferences');
    expect(s.q('preferences-retry')).not.toBeNull();
    expect(s.q('preferences-loading')).toBeNull();
  });

  it('says a failed load, not a skeleton, when no answer comes in time (stream down, no network)', async () => {
    const s = await mountPanel(PreferencesForm);
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    expect(s.q('preferences-error')?.textContent).toContain('We could not load your preferences');
    expect(s.q('preferences-retry')?.textContent).toContain('Retry');
    expect(s.q('preferences-loading')).toBeNull();
    expect(s.q('preferences-theme')).toBeNull();
  });

  it('«Retry» opens the stream again and shows the preferences when they come', async () => {
    const s = await mountPanel(PreferencesForm);
    await s.live();
    await s.clock.advance(LIVE_TIMEOUT_MS);
    const before = s.net.streams.length;
    s.q('preferences-retry')?.click();
    await flush();
    expect(s.net.streams.length).toBe(before + 1);
    expect(s.q('preferences-error')).toBeNull();
    expect(s.q('preferences-loading')).not.toBeNull();
    const stream = s.net.lastStream();
    stream.push(HELLO);
    await s.result(stream, 'accounts.preferences.get', preferences({ theme_mode: 'dark' }));
    expect(s.q('preferences-loading')).toBeNull();
    expect(ionProps(s.q('preferences-theme'), 'value')).toEqual({ value: 'dark' });
  });

  it('makes «System / Light / Dark» a 44px target on touch (audit 2026-10-14, R-13)', () => {
    // happy-dom lays nothing out: the component's stylesheet is read, with the touch query of `@erplora/ui`.
    const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'PreferencesForm.vue'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\s+/g, ' ');
    const touch = /@media \(pointer: coarse\), \(max-width: 834px\) \{ \.theme-segment ion-segment-button \{([^}]*)\}/.exec(css);
    expect(touch?.[1]).toContain('min-height: 44px');
  });
});
