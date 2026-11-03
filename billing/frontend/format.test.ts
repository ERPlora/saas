// How the Store says money and dates: euros in the person's language («29,99 €», «€29.99»), from the
// cents billing sends (`apps.Module` prices, Stripe's previews) or the decimal strings of a plan
// (`hubs.PlanOut`), and a renewal as a date without the time («1 nov 2026»).
// clock: data only — no code under test compares these dates with now.
import { describe, expect, it } from 'vitest';

import { formatCents, formatDate, formatEuros } from './format';

/** Intl keeps the euro sign with its number: a no-break space, not a space. */
const nb = (text: string) => text.replace(' ', '\u00a0');

describe('formatCents', () => {
  it('says cents as euros in the person’s language', () => {
    expect(formatCents(900, 'es')).toBe(nb('9,00 €'));
    expect(formatCents(900, 'en')).toBe('€9.00');
    expect(formatCents(36288, 'es')).toBe(nb('362,88 €'));
  });

  it('says zero as zero, never as nothing', () => {
    expect(formatCents(0, 'en')).toBe('€0.00');
  });
});

describe('formatEuros', () => {
  it('says the decimal string of a plan price', () => {
    expect(formatEuros('29.99', 'es')).toBe(nb('29,99 €'));
    expect(formatEuros('299.90', 'en')).toBe('€299.90');
  });

  it('says a twelfth of a year to the cent', () => {
    expect(formatEuros(299.9 / 12, 'es')).toBe(nb('24,99 €'));
  });
});

describe('formatDate', () => {
  it('says the day, without the time, in the person’s language', () => {
    expect(formatDate('2026-11-01T10:00:00Z', 'es', 'Europe/Madrid')).toBe('1 nov 2026');
    expect(formatDate('2026-11-01T10:00:00Z', 'en', 'Europe/Madrid')).toBe('Nov 1, 2026');
  });

  it('says a unix timestamp (Stripe’s) too', () => {
    expect(formatDate(1793527200, 'en', 'Europe/Madrid')).toBe('Nov 1, 2026');
  });

  it('nothing to say without a date', () => {
    expect(formatDate(null, 'en')).toBe('');
  });
});
