// How a business's status reads everywhere (the launcher, Businesses, a business's page): the ui's pill
// (`businessStatusPill`), a danger pill of our own when the Hub refused to prepare the business, and
// the catalogue key of the sentence that says why «Open» does not work or what to do. Inside the apps
// the sentence never invites to pay (README §4): it says to go to erplora.com, without a link. An unpaid
// invoice says its real deadline (audit 2026-10-14, R-06): the server suspends the business 7 days after the
// invoice went unpaid (`billing.services.UNPAID_PLAN_GRACE`), so the date is `unpaid_since` + 7 days, said as
// a day (never «7 more days», never the minute).
import { businessStatusPill, type BusinessStatus, formatDateTime, type StatusPillSpec } from '@erplora/ui/components';

import { formatDate } from '../../billing/frontend/format';
import type { BusinessStatusCode, OpenBlockedReason } from '../../frontend/sdk-types';

/** What both a row of the list and a business's detail carry. */
export interface BusinessState {
  status: BusinessStatusCode;
  open_blocked_reason?: OpenBlockedReason | null;
  hub_error?: string | null;
  /** Since when its invoice is unpaid (past due or suspended). */
  unpaid_since?: string | null;
  /** Deleted: until when it can be recovered. */
  purge_after?: string | null;
}

/** The grace of an unpaid invoice before the business is suspended (`billing.services.UNPAID_PLAN_GRACE`). */
const GRACE_MS = 7 * 24 * 60 * 60 * 1000;

/** When a business unpaid since `since` is suspended (ISO 8601); `''` when unknown. */
export function unpaidDeadline(since: string | null | undefined): string {
  if (!since) return '';
  const start = Date.parse(since);
  return Number.isNaN(start) ? '' : new Date(start + GRACE_MS).toISOString();
}

/** The Hub refused to prepare it: a business being prepared with the Hub's last error. */
export function preparationFailed(business: BusinessState): boolean {
  return business.open_blocked_reason === 'error' || (business.status === 'preparing' && !!business.hub_error);
}

/** The pill of the business's status; `t` translates the panel's own «Not prepared». */
export function statusPill(business: BusinessState, t: (key: string) => string, locale: string): StatusPillSpec {
  if (preparationFailed(business)) return { tone: 'danger', label: t('hubs.status.error'), busy: false };
  return businessStatusPill(business.status as BusinessStatus, locale);
}

/** The catalogue key of the sentence under a business that is not simply active; `null` if it is. */
export function reasonKey(business: BusinessState, inApp: boolean): string | null {
  if (preparationFailed(business)) return 'hubs.reason.error';
  switch (business.status) {
    case 'preparing':
      return 'hubs.reason.preparing';
    case 'past_due':
      if (unpaidDeadline(business.unpaid_since)) return inApp ? 'hubs.reason.pastDueUntilApp' : 'hubs.reason.pastDueUntil';
      return inApp ? 'hubs.reason.pastDueApp' : 'hubs.reason.pastDue';
    case 'suspended':
      if (business.unpaid_since) return inApp ? 'hubs.reason.suspendedSinceApp' : 'hubs.reason.suspendedSince';
      return inApp ? 'hubs.reason.suspendedApp' : 'hubs.reason.suspended';
    case 'deleting':
      return 'hubs.reason.deleting';
    default:
      return null;
  }
}

/** The `{date}` of the reason's sentence: the deadline of an unpaid invoice, since when a business is suspended
 *  (both a day) or until when a deleted one can be recovered; `''` for the rest. */
export function reasonDate(business: BusinessState, locale: string): string {
  switch (business.status) {
    case 'past_due':
      return formatDate(unpaidDeadline(business.unpaid_since), locale);
    case 'suspended':
      return formatDate(business.unpaid_since, locale);
    case 'deleting':
      return business.purge_after ? formatDateTime(business.purge_after, locale) : '';
    default:
      return '';
  }
}

/** Suspended or deleted, «Open» is not offered at all (README §5.3); otherwise it is, disabled while it
 *  does not serve (`can.open`). */
export function opensAtAll(business: { status: BusinessStatusCode }): boolean {
  return business.status !== 'suspended' && business.status !== 'deleting';
}
