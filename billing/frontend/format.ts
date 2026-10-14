// How the Store says money and dates. Money is euros in the person's language («29,99 €», «€29.99»), from
// the cents billing sends (`apps.Module` prices, Stripe's previews) or the decimal strings of a plan
// (`hubs.PlanOut`); a renewal is a day without the time («1 nov 2026»). Pages never format by hand.

const money = new Map<string, Intl.NumberFormat>();
const days = new Map<string, Intl.DateTimeFormat>();

function euros(locale: string): Intl.NumberFormat {
  let found = money.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' });
    money.set(locale, found);
  }
  return found;
}

/** Cents (an integer, as Stripe charges) as euros. */
export function formatCents(cents: number, locale: string): string {
  return euros(locale).format(cents / 100);
}

/** A price in euros (a plan's decimal string, or a number) as euros. */
export function formatEuros(amount: string | number, locale: string): string {
  return euros(locale).format(Math.floor(Number(amount) * 100 + 1e-6) / 100);
}

/** The day of `value` (ISO 8601, or Stripe's unix seconds) without the time; `''` without one. */
export function formatDate(value: string | number | null | undefined, locale: string, timeZone?: string): string {
  if (value === null || value === undefined || value === '') return '';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const key = `${locale}|${timeZone ?? ''}`;
  let found = days.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone });
    days.set(key, found);
  }
  return found.format(date);
}
