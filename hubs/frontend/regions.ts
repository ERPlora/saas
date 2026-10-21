// The countries a business may be created in and the time zones its settings offer. Both lists are the
// server's: `COUNTRIES` mirrors hubs/schemas.py (the EU-27 ERPlora serves) and the zones are each
// country's starting zone of hubs/services.py `TIME_ZONES` plus the Atlantic islands of Spain and
// Portugal (guard: regions.test.ts). Names come from Intl in the person's language, never from a
// catalogue of ours.

/** The markets ERPlora serves (hubs/schemas.py `COUNTRIES`). */
export const COUNTRIES = [
  'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE',
  'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE',
] as const;

/** Where a new business starts: most of ERPlora's customers are in Spain. */
export const DEFAULT_COUNTRY = 'ES';

/** The country the browser's languages suggest (`fr-BE` → BE, `de` → DE, its main country): the first that
 *  ERPlora serves, else Spain. Only a suggestion: the person picks another in the form. */
export function suggestedCountry(languages: readonly string[]): string {
  const served: readonly string[] = COUNTRIES;
  for (const tag of languages) {
    let region: string | undefined;
    try {
      region = new Intl.Locale(tag).maximize().region;
    } catch {
      continue;
    }
    if (region && served.includes(region)) return region;
  }
  return DEFAULT_COUNTRY;
}

/** Each country's starting zone (hubs/services.py `TIME_ZONES`) and the Atlantic islands. */
const TIME_ZONES = [
  'Europe/Vienna', 'Europe/Brussels', 'Europe/Sofia', 'Europe/Zagreb', 'Asia/Nicosia', 'Europe/Prague',
  'Europe/Copenhagen', 'Europe/Tallinn', 'Europe/Helsinki', 'Europe/Paris', 'Europe/Berlin',
  'Europe/Athens', 'Europe/Budapest', 'Europe/Dublin', 'Europe/Rome', 'Europe/Riga', 'Europe/Vilnius',
  'Europe/Luxembourg', 'Europe/Malta', 'Europe/Amsterdam', 'Europe/Warsaw', 'Europe/Lisbon',
  'Europe/Bucharest', 'Europe/Bratislava', 'Europe/Ljubljana', 'Europe/Madrid', 'Europe/Stockholm',
  'Atlantic/Canary', 'Atlantic/Madeira', 'Atlantic/Azores',
];

export interface Option {
  value: string;
  label: string;
}

const regionNames = new Map<string, Intl.DisplayNames>();

/** The country's name in `locale` (`ES` → «España»); an unknown code as it came. */
export function countryName(code: string, locale: string): string {
  let names = regionNames.get(locale);
  if (!names) {
    names = new Intl.DisplayNames([locale, 'en'], { type: 'region', fallback: 'code' });
    regionNames.set(locale, names);
  }
  return names.of(code) ?? code;
}

const byLabel = (locale: string) => (a: Option, b: Option) => a.label.localeCompare(b.label, locale);

/** The countries as select options, by name in `locale`. */
export function countryOptions(locale: string): Option[] {
  return COUNTRIES.map((code) => ({ value: code, label: countryName(code, locale) })).sort(byLabel(locale));
}

/** «Madrid (Central European Time)»: the zone's city and its time's generic name, true all year (audit 2 R-31: an
 *  offset, «GMT+2», stops being true when the clocks change). `at` only picks the name where it has several. */
export function timeZoneLabel(zone: string, locale: string, at: Date = new Date()): string {
  const city = zone.slice(zone.lastIndexOf('/') + 1).replace(/_/g, ' ');
  let name = '';
  try {
    const parts = new Intl.DateTimeFormat(locale, { timeZone: zone, timeZoneName: 'longGeneric' }).formatToParts(at);
    name = parts.find((part) => part.type === 'timeZoneName')?.value ?? '';
  } catch {
    // An unknown zone keeps its name alone.
  }
  return name ? `${city} (${name})` : city;
}

/** The zones as select options, by label; `current` (the business's own) is kept when not listed. */
export function timeZoneOptions(locale: string, current?: string): Option[] {
  const zones = current && !TIME_ZONES.includes(current) ? [...TIME_ZONES, current] : TIME_ZONES;
  return zones.map((zone) => ({ value: zone, label: timeZoneLabel(zone, locale) })).sort(byLabel(locale));
}
