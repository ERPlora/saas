// The day of a business's usage (`hubs.usage.get` / `business.usage.day`, `YYYY-MM-DD`, the UTC day the Hub
// measured): whether it is yesterday where the person is («Datos de ayer», mockups `business.html`), and
// its short name otherwise («9 oct», with the year only when it is not this one).
import { describe, expect, it } from 'vitest';

import { formatUsageDay, isYesterday } from './usage-day';

describe('isYesterday', () => {
  it('is the day before today on the device', () => {
    const now = new Date(2026, 9, 14, 10, 0);
    expect(isYesterday('2026-10-13', now)).toBe(true);
    expect(isYesterday('2026-10-14', now)).toBe(false);
    expect(isYesterday('2026-10-12', now)).toBe(false);
  });

  it('crosses a month and a year', () => {
    expect(isYesterday('2026-09-30', new Date(2026, 9, 1, 0, 30))).toBe(true);
    expect(isYesterday('2025-12-31', new Date(2026, 0, 1, 23, 59))).toBe(true);
  });

  it('a value that is not a day is never yesterday', () => {
    expect(isYesterday('', new Date(2026, 9, 14))).toBe(false);
    expect(isYesterday('yesterday', new Date(2026, 9, 14))).toBe(false);
  });
});

describe('formatUsageDay', () => {
  const now = new Date(2026, 9, 14, 10, 0);

  it('names the day and its month, short, in the language asked for', () => {
    expect(formatUsageDay('2026-10-09', 'en', now)).toBe('Oct 9');
    expect(formatUsageDay('2026-10-09', 'es', now)).toBe('9 oct');
  });

  it('is the calendar day measured, whatever the device zone', () => {
    // Midnight UTC is still the 8th in America: the day is a date, not an instant.
    expect(formatUsageDay('2026-10-09', 'en', now)).not.toContain('8');
  });

  it('adds the year when it is not this one', () => {
    expect(formatUsageDay('2025-12-30', 'en', now)).toBe('Dec 30, 2025');
    expect(formatUsageDay('2025-12-30', 'es', now)).toBe('30 dic 2025');
  });

  it('a broken language falls back to English; a value that is not a day comes back as it came', () => {
    expect(formatUsageDay('2026-10-09', 'not a language!', now)).toBe('Oct 9');
    expect(formatUsageDay('soon', 'en', now)).toBe('soon');
  });
});
