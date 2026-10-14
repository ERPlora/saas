// The countries a business may be created in and the time zones its settings offer: the server's lists
// (hubs/schemas.py `COUNTRIES`, hubs/services.py `TIME_ZONES`), named in the person's language by Intl,
// never by a catalogue of ours.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { COUNTRIES, countryName, countryOptions, DEFAULT_COUNTRY, timeZoneLabel, timeZoneOptions } from './regions';

const HUBS = join(dirname(fileURLToPath(import.meta.url)), '..');

describe('countries', () => {
  it('are exactly the markets the server accepts (hubs/schemas.py COUNTRIES)', () => {
    const schemas = readFileSync(join(HUBS, 'schemas.py'), 'utf8');
    const listed = /COUNTRIES = frozenset\(\s*"([A-Z ]+)"\.split\(\)/.exec(schemas)?.[1].split(' ') ?? [];
    expect(listed.length).toBe(27);
    expect([...COUNTRIES].sort()).toEqual(listed.sort());
  });

  it('start on Spain, and are named in the language asked for', () => {
    expect(DEFAULT_COUNTRY).toBe('ES');
    expect(countryName('ES', 'es')).toBe('España');
    expect(countryName('ES', 'en')).toBe('Spain');
    expect(countryName('DE', 'es')).toBe('Alemania');
  });

  it('are offered by their name, in alphabetical order of that language', () => {
    const es = countryOptions('es');
    expect(es).toHaveLength(27);
    expect(es.find((option) => option.value === 'ES')?.label).toBe('España');
    const labels = es.map((option) => option.label);
    expect(labels).toEqual([...labels].sort((a, b) => a.localeCompare(b, 'es')));
    expect(countryOptions('en')[0]).toEqual({ value: 'AT', label: 'Austria' });
  });

  it('keep an unknown code as it came, never an empty label', () => {
    expect(countryName('XX', 'en')).toBe('XX');
  });
});

describe('time zones', () => {
  it("offer every country's starting zone (hubs/services.py TIME_ZONES) and the Spanish and Portuguese islands", () => {
    const services = readFileSync(join(HUBS, 'services.py'), 'utf8');
    const block = /TIME_ZONES = \{([^}]+)\}/.exec(services)?.[1] ?? '';
    const zones = [...block.matchAll(/"[A-Z]{2}": "([^"]+)"/g)].map((m) => m[1]);
    expect(zones.length).toBe(27);
    const offered = timeZoneOptions('en').map((option) => option.value);
    for (const zone of [...zones, 'Atlantic/Canary', 'Atlantic/Madeira', 'Atlantic/Azores']) {
      expect(offered, zone).toContain(zone);
    }
  });

  it('name a zone by its city and its offset now', () => {
    const winter = new Date('2026-01-15T12:00:00Z');
    expect(timeZoneLabel('Europe/Madrid', 'en', winter)).toBe('Madrid (GMT+1)');
    expect(timeZoneLabel('Atlantic/Canary', 'en', winter)).toBe('Canary (GMT+0)');
    expect(timeZoneLabel('Europe/Helsinki', 'es', winter)).toBe('Helsinki (GMT+2)');
  });

  it("keep the business's own zone when it is not in the list, so a select never loses its value", () => {
    const options = timeZoneOptions('en', 'America/New_York');
    expect(options.map((option) => option.value)).toContain('America/New_York');
    expect(options.find((option) => option.value === 'America/New_York')?.label).toMatch(/^New York \(/);
  });
});
