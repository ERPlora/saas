// How the Store says money and dates. Money is euros in the person's language («29,99 €», «€29.99»), from
// the cents billing sends (`apps.Module` prices, Stripe's previews) or the decimal strings of a plan
// (`hubs.PlanOut`), written by `formatMoney` like every amount of the panel (thousands grouped from four digits,
// «1.099,90 €»); a renewal is a day without the time («1 nov 2026»). Pages never format by hand.
import { formatMoney, type Money } from '@erplora/ui/components';

const EUROS: Money = { currency: 'EUR', decimals: 2 };
const days = new Map<string, Intl.DateTimeFormat>();

/** Cents (an integer, as Stripe charges) as euros. */
export function formatCents(cents: number, locale: string): string {
  return formatMoney(cents, locale, EUROS);
}

/** A price in euros (a plan's decimal string, or a number) as euros, to the cent below. */
export function formatEuros(amount: string | number, locale: string): string {
  return formatMoney(Math.floor(Number(amount) * 100 + 1e-6), locale, EUROS);
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
