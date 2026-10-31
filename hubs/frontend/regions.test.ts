// The countries a business may be created in and the time zones its settings offer: the server's lists
// (hubs/schemas.py `COUNTRIES`, hubs/services.py `TIME_ZONES`), named in the person's language by Intl,
// never by a catalogue of ours.
// clock: data only — no code under test compares these dates with now.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  COUNTRIES,
  countryName,
  countryOptions,
  DEFAULT_COUNTRY,
  suggestedCountry,
  timeZoneLabel,
  timeZoneOptions,
} from './regions';

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

// flow: HUBS-F01 (HUBS-G65, old saas SAAS_DASHBOARD-F01): «the country comes suggested by the browser's language».
describe('the country the browser suggests', () => {
  it("is the region of the first language whose country ERPlora serves", () => {
    expect(suggestedCountry(['fr-BE', 'fr'])).toBe('BE');
    expect(suggestedCountry(['en-US', 'de-AT'])).toBe('AT');
  });

  it('reads a language without a region as its main country', () => {
    expect(suggestedCountry(['de'])).toBe('DE');
    expect(suggestedCountry(['it'])).toBe('IT');
  });

  it('is Spain when no language names a country ERPlora serves, or the tag is not one', () => {
    expect(suggestedCountry(['en-US', 'ja'])).toBe(DEFAULT_COUNTRY);
    expect(suggestedCountry([])).toBe(DEFAULT_COUNTRY);
    expect(suggestedCountry(['not a tag'])).toBe(DEFAULT_COUNTRY);
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

  it('name a zone by its city and its time, true all year (audit 2 R-31: «Madrid (GMT+2)» stopped being true on Oct 25)', () => {
    const winter = new Date('2026-01-15T12:00:00Z');
    const summer = new Date('2026-07-15T12:00:00Z');
    expect(timeZoneLabel('Europe/Madrid', 'en', winter)).toBe('Madrid (Central European Time)');
    expect(timeZoneLabel('Europe/Madrid', 'en', summer)).toBe('Madrid (Central European Time)');
    expect(timeZoneLabel('Atlantic/Canary', 'es', summer)).toBe('Canary (hora de Europa occidental)');
    expect(timeZoneLabel('Europe/Helsinki', 'es', winter)).toBe('Helsinki (hora de Europa oriental)');
  });

  it("keep the business's own zone when it is not in the list, so a select never loses its value", () => {
    const options = timeZoneOptions('en', 'America/New_York');
    expect(options.map((option) => option.value)).toContain('America/New_York');
    expect(options.find((option) => option.value === 'America/New_York')?.label).toMatch(/^New York \(/);
  });
});
