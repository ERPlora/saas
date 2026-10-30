// What «Download the data» says of a copy of a business's data (DataCopyCard): its size, in the person's language.

const UNITS = ['kilobyte', 'megabyte', 'gigabyte', 'terabyte'] as const;

/** `bytes` as kB, MB, GB or TB (1024 each, from kB up: a copy is never a few bytes), one decimal at most. */
export function formatBytes(bytes: number, locale: string): string {
  let value = Math.max(0, bytes) / 1024;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return new Intl.NumberFormat(locale, {
    style: 'unit',
    unit: UNITS[unit],
    unitDisplay: 'short',
    maximumFractionDigits: 1,
  }).format(value);
}
