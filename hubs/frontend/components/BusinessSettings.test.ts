// The Settings of a business, «General» (mockups `business.html` «settings»): name, country, time
// zone and language (`hubs.business.update`, only what changed), and the web address, which does not
// change (the devices use it), with «Copy». «Save changes» waits for a change.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

import { toastSuccess } from '@erplora/ui/shell';

import { apiError, flush, ionProps, mountHubs, optionValue } from '../__tests__/mount-hubs';
import BusinessSettings from './BusinessSettings.vue';
import CopyField from './CopyField.vue';

const BUSINESS = {
  id: 'h1',
  name: 'Panadería López',
  host: 'bakery.erplora.com',
  country: 'ES',
  timezone: 'Europe/Madrid',
  language: 'es',
  status: 'active',
  country_locked: false,
};

afterEach(() => {
  vi.mocked(toastSuccess).mockClear();
  document.body.innerHTML = '';
});

async function setup(api: () => Response = () => Response.json({ ...BUSINESS, name: 'Panadería Dulce' }), business = BUSINESS) {
  const current = ref<Record<string, unknown>>(business);
  const m = await mountHubs({ render: () => h(BusinessSettings, { business: current.value as never }) }, { api });
  const get = (id: string) => m.wrapper.get(`[data-testid="${id}"]`);
  async function type(id: string, value: string) {
    get(id).element.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function pick(id: string, value: string) {
    get(id).element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  return { ...m, get, type, pick, current };
}

describe('BusinessSettings', () => {
  it('shows the business as it is, in outlined md fields, and its address to copy', async () => {
    const s = await setup();
    expect(ionProps(s.get('settings-name'), 'value', 'mode', 'fill', 'label')).toEqual({
      value: 'Panadería López',
      mode: 'md',
      fill: 'outline',
      label: 'Business name',
    });
    expect(ionProps(s.get('settings-country'), 'value', 'interface')).toEqual({ value: 'ES', interface: 'popover' });
    expect(ionProps(s.get('settings-timezone'), 'value')).toEqual({ value: 'Europe/Madrid' });
    expect(ionProps(s.get('settings-language'), 'value')).toEqual({ value: 'es' });
    expect(s.get('settings-language').findAll('ion-select-option').map((o) => [optionValue(o), o.text()])).toEqual([
      ['en', 'English'],
      ['es', 'Español'],
    ]);
    expect(s.wrapper.getComponent(CopyField).props()).toEqual({ value: 'bakery.erplora.com', label: 'Web address (it does not change: your devices use it)' });
  });

  it('«Save changes» waits for a change', async () => {
    const s = await setup();
    expect(ionProps(s.get('settings-save'), 'disabled')).toEqual({ disabled: true });
    expect(s.get('settings-save-hint').text()).toBe('Enabled when you change something.');
    await s.type('settings-name', 'Panadería Dulce');
    expect(ionProps(s.get('settings-save'), 'disabled')).toEqual({ disabled: false });
    await s.type('settings-name', 'Panadería López');
    expect(ionProps(s.get('settings-save'), 'disabled')).toEqual({ disabled: true });
  });

  it('sends only what changed, says so, and waits for the next change', async () => {
    const s = await setup();
    await s.type('settings-name', '  Panadería Dulce ');
    await s.pick('settings-timezone', 'Atlantic/Canary');
    await s.get('settings-save').trigger('click');
    await flush();
    expect(s.calls().map((c) => [c.path, c.body])).toEqual([
      ['/api/hubs/businesses/update', { id: 'h1', name: 'Panadería Dulce', timezone: 'Atlantic/Canary' }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Changes saved');
  });

  it('puts the server’s field errors on their fields', async () => {
    const s = await setup(() => apiError(422, 'invalid_payload', 'Invalid payload', { timezone: 'Choose a valid time zone.' }));
    await s.pick('settings-timezone', 'Atlantic/Canary');
    await s.get('settings-save').trigger('click');
    await flush();
    expect(ionProps(s.get('settings-timezone'), 'errorText')).toEqual({ errorText: 'Choose a valid time zone.' });
  });

  it('says any other refusal above the button', async () => {
    const s = await setup(() => apiError(409, 'hubs.business_deleted', 'This business was deleted.'));
    await s.type('settings-name', 'Otro');
    await s.get('settings-save').trigger('click');
    await flush();
    expect(s.get('settings-error').text()).toContain('This business was deleted.');
  });

  it('follows the business when it changes elsewhere, unless the person is editing', async () => {
    const s = await setup();
    s.current.value = { ...BUSINESS, name: 'Nuevo nombre' };
    await flush();
    expect(ionProps(s.get('settings-name'), 'value')).toEqual({ value: 'Nuevo nombre' });
  });

  it('once ready the country is read-only text with why under it, not a disabled select (audit 2 R-31)', async () => {
    const s = await setup(undefined, { ...BUSINESS, country_locked: true });
    const country = s.get('settings-country');
    expect(country.element.tagName).not.toBe('ION-SELECT');
    expect(country.text()).toContain('Country');
    expect(country.text()).toContain('Spain');
    // Its reason right under it, not under the next row.
    expect(country.get('[data-testid="settings-country-locked"]').text()).toBe(
      'The country cannot change once the business is ready: its invoices belong to one country.',
    );
    expect(ionProps(s.get('settings-name'), 'disabled')).toEqual({ disabled: false });
  });

  it('a country the server refuses to change is said', async () => {
    const s = await setup(() => apiError(409, 'hubs.country_locked', 'The country cannot change once the business is ready.'));
    await s.pick('settings-country', 'PT');
    await s.get('settings-save').trigger('click');
    await flush();
    expect(s.get('settings-error').text()).toContain('The country cannot change once the business is ready.');
  });

  it('a lost connection is said in the person’s language', async () => {
    const s = await setup(() => Promise.reject(new TypeError('Failed to fetch')) as never);
    await s.type('settings-name', 'Otro');
    await s.get('settings-save').trigger('click');
    await flush();
    expect(s.get('settings-error').text()).toContain('We could not reach ERPlora. Check your connection and try again.');
  });

  it('a deleted business cannot be edited', async () => {
    const s = await setup(undefined, { ...BUSINESS, status: 'deleting' });
    expect(ionProps(s.get('settings-name'), 'disabled')).toEqual({ disabled: true });
    expect(ionProps(s.get('settings-save'), 'disabled')).toEqual({ disabled: true });
  });
});
