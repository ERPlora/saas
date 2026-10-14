// How a session's device and browser read on Account → Security (mockups `account.html`): the server sends a code
// (`accounts.devices.describe`) and the panel names it in the reader's language: «Mac (macOS)», «PC con Windows»,
// «App ERPlora 4.0».
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { session } from './__tests__/mount-panel';
import { browserName, deviceIcon, deviceName, isAppSession } from './devices';
import en from './locale/en.json';
import es from './locale/es.json';

function translator(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return (key: string, params?: Record<string, unknown>) => i18n.global.t(key, params ?? {});
}

describe('deviceName', () => {
  it('names every device code the server sends, in English and Spanish', () => {
    const t = translator('es');
    expect(deviceName(t, 'mac')).toBe('Mac (macOS)');
    expect(deviceName(t, 'windows')).toBe('PC con Windows');
    expect(deviceName(t, 'iphone')).toBe('iPhone');
    expect(deviceName(t, 'ipad')).toBe('iPad');
    expect(deviceName(t, 'android')).toBe('Android');
    expect(deviceName(t, 'chromeos')).toBe('Chromebook');
    expect(deviceName(t, 'linux')).toBe('PC con Linux');
    expect(deviceName(translator('en'), 'windows')).toBe('Windows PC');
  });

  it('says an unknown device instead of a blank or a raw code', () => {
    expect(deviceName(translator('en'), '')).toBe('Unknown device');
    expect(deviceName(translator('es'), 'playstation')).toBe('Dispositivo desconocido');
  });
});

describe('browserName', () => {
  it('is the browser and its version, a proper noun', () => {
    expect(browserName(translator('es'), session(1, { browser: 'Chrome', browser_version: '130' }))).toBe('Chrome 130');
    expect(browserName(translator('es'), session(1, { browser: 'Safari', browser_version: '' }))).toBe('Safari');
  });

  it('is the ERPlora app and its version inside the app', () => {
    const row = session(1, { browser: '', browser_version: '', app_version: '4.0' });
    expect(browserName(translator('es'), row)).toBe('App ERPlora 4.0');
    expect(browserName(translator('en'), row)).toBe('ERPlora app 4.0');
    expect(isAppSession(row)).toBe(true);
    expect(isAppSession(session(2))).toBe(false);
  });

  it('says an unknown browser instead of a blank', () => {
    expect(browserName(translator('en'), session(1, { browser: '', browser_version: '' }))).toBe('Unknown browser');
  });
});

describe('deviceIcon', () => {
  it('is a phone for a phone or a tablet, a laptop for a computer (mockups `account.html`)', () => {
    expect(deviceIcon('iphone')).toBe('ion:phone-portrait-outline');
    expect(deviceIcon('android')).toBe('ion:phone-portrait-outline');
    expect(deviceIcon('ipad')).toBe('ion:phone-portrait-outline');
    expect(deviceIcon('mac')).toBe('ion:laptop-outline');
    expect(deviceIcon('')).toBe('ion:laptop-outline');
  });
});
