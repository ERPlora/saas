// The day of a business's usage (`business.usage.day`, `YYYY-MM-DD`): the UTC day the Hub measured, a
// calendar date, not an instant. The «Usage» card says «yesterday» when it is the day before today where
// the person is, and its short name otherwise (mockups `business.html`, «Datos de ayer»).

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
/** The language of the app's source texts: what a broken locale falls back to. */
const FALLBACK_LOCALE = 'en';

function localDay(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Whether `day` is the day before `now`'s, in the device's calendar. */
export function isYesterday(day: string, now: Date = new Date()): boolean {
  if (!DAY.test(day)) return false;
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  return day === localDay(yesterday);
}

function formatter(locale: string, withYear: boolean): Intl.DateTimeFormat {
  const options: Intl.DateTimeFormatOptions = {
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
    // The day is read at midnight UTC and shown in UTC: the same date on every device.
    timeZone: 'UTC',
  };
  try {
    return new Intl.DateTimeFormat(locale, options);
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    return new Intl.DateTimeFormat(FALLBACK_LOCALE, options);
  }
}

/** `day` short in `locale` («Oct 9», «9 oct»), with its year when it is not `now`'s; a non-day as it came. */
export function formatUsageDay(day: string, locale: string, now: Date = new Date()): string {
  const match = DAY.exec(day);
  if (!match) return day;
  const withYear = Number(match[1]) !== now.getFullYear();
  return formatter(locale, withYear).format(new Date(`${day}T00:00:00Z`));
}
