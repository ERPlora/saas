// Account → Preferences (mockups `account.html` «preferences»): appearance (system, light, dark: the shell's theme,
// painted at once and kept in the account), language (the account's, which the mails and the jump to a business
// read too) and the two mail switches («Invoices and payments» is always on). Each control saves on its own
// (`accounts.preferences.update`, only what changed) and says so; a refusal puts the control back.
import { setThemeMode, themeMode } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError, toastSuccess } from '@erplora/ui/shell';

import { type ApiCall, apiError, choose, errorFrame, flush, ionProps, mountPanel, preferences, subId } from '../__tests__/mount-panel';
import type { PreferencesOut } from '../../../frontend/sdk-types';
import PreferencesForm from './PreferencesForm.vue';

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  setThemeMode('system');
  document.documentElement.lang = '';
  document.body.innerHTML = '';
});

async function setup(now: PreferencesOut = preferences(), api: (call: ApiCall) => Response | Promise<Response> = () => Response.json(now)) {
  const s = await mountPanel(PreferencesForm, { api });
  const stream = await s.live();
  await s.result(stream, 'accounts.preferences.get', now);
  return { ...s, stream };
}

describe('PreferencesForm', () => {
  it('shows the account’s preferences and paints its theme', async () => {
    const s = await setup(preferences({ theme_mode: 'dark', hub_alerts: true, marketing_emails: false }));
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
    expect(ionProps(s.q('preferences-marketing'), 'checked')).toEqual({ checked: false });
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

  it('saves each mail switch on its own', async () => {
    const s = await setup(preferences(), () => Response.json(preferences({ marketing_emails: true })));
    await choose(s.q('preferences-marketing'), { checked: true });
    await choose(s.q('preferences-hub-alerts'), { checked: false });
    expect(s.calls().map((c) => c.body)).toEqual([{ marketing_emails: true }, { hub_alerts: false }]);
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
  });
});
