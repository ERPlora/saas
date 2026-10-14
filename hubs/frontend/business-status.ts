// How a business's status reads everywhere (the launcher, Businesses, a business's page): the ui's pill
// (`businessStatusPill`), a danger pill of our own when the Hub refused to prepare the business, and
// the catalogue key of the sentence that says why «Open» does not work or what to do. Inside the apps
// the sentence never invites to pay (README §4): it says to go to erplora.com, without a link.
import { businessStatusPill, type BusinessStatus, type StatusPillSpec } from '@erplora/ui/components';

import type { BusinessStatusCode, OpenBlockedReason } from '../../frontend/sdk-types';

/** What both a row of the list and a business's detail carry. */
export interface BusinessState {
  status: BusinessStatusCode;
  open_blocked_reason?: OpenBlockedReason | null;
  hub_error?: string | null;
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
      return inApp ? 'hubs.reason.pastDueApp' : 'hubs.reason.pastDue';
    case 'suspended':
      return inApp ? 'hubs.reason.suspendedApp' : 'hubs.reason.suspended';
    case 'deleting':
      return 'hubs.reason.deleting';
    default:
      return null;
  }
}

/** Suspended or deleted, «Open» is not offered at all (README §5.3); otherwise it is, disabled while it
 *  does not serve (`can.open`). */
export function opensAtAll(business: { status: BusinessStatusCode }): boolean {
  return business.status !== 'suspended' && business.status !== 'deleting';
}
