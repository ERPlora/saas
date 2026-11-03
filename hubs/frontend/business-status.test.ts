// How a business's status is painted everywhere (launcher, Businesses, its page): the ui's pill for the
// status, a danger pill when the Hub refused to prepare it, and the sentence that says why «Open» does
// not work (or what to do), which inside the apps never points at a payment page.
// clock: data only — no code under test compares these dates with now.
import { describe, expect, it } from 'vitest';

import { reasonDate, reasonKey, statusPill, unpaidDeadline } from './business-status';

const t = (key: string) => `t:${key}`;

describe('statusPill', () => {
  it("is the ui's pill of the status, in the language asked for", () => {
    expect(statusPill({ status: 'active', open_blocked_reason: null }, t, 'es')).toEqual({ tone: 'success', label: 'Activo', busy: false });
    expect(statusPill({ status: 'preparing', open_blocked_reason: 'preparing' }, t, 'en')).toEqual({ tone: 'info', label: 'Preparing', busy: true });
    expect(statusPill({ status: 'past_due', open_blocked_reason: null }, t, 'en').tone).toBe('warning');
    expect(statusPill({ status: 'suspended', open_blocked_reason: 'suspended' }, t, 'en').tone).toBe('danger');
    expect(statusPill({ status: 'deleting', open_blocked_reason: 'deleting' }, t, 'en').tone).toBe('danger');
  });

  it('is a danger pill of its own when the Hub refused to prepare the business', () => {
    expect(statusPill({ status: 'preparing', open_blocked_reason: 'error' }, t, 'en')).toEqual({
      tone: 'danger',
      label: 't:hubs.status.error',
      busy: false,
    });
  });
});

describe('reasonKey', () => {
  it('says nothing for an active business', () => {
    expect(reasonKey({ status: 'active', open_blocked_reason: null }, false)).toBeNull();
  });

  it('explains every other status, the app sentence without a link to pay', () => {
    expect(reasonKey({ status: 'preparing', open_blocked_reason: 'preparing' }, false)).toBe('hubs.reason.preparing');
    expect(reasonKey({ status: 'preparing', open_blocked_reason: 'error' }, false)).toBe('hubs.reason.error');
    expect(reasonKey({ status: 'past_due', open_blocked_reason: null }, false)).toBe('hubs.reason.pastDue');
    expect(reasonKey({ status: 'past_due', open_blocked_reason: null }, true)).toBe('hubs.reason.pastDueApp');
    expect(reasonKey({ status: 'suspended', open_blocked_reason: 'suspended' }, false)).toBe('hubs.reason.suspended');
    expect(reasonKey({ status: 'suspended', open_blocked_reason: 'suspended' }, true)).toBe('hubs.reason.suspendedApp');
    expect(reasonKey({ status: 'deleting', open_blocked_reason: 'deleting' }, false)).toBe('hubs.reason.deleting');
  });
});

describe('the real deadline of an unpaid invoice (audit 2026-10-14, R-06)', () => {
  it('is 7 days after the invoice went unpaid, as the server suspends it (billing UNPAID_PLAN_GRACE)', () => {
    expect(unpaidDeadline('2026-10-10T14:23:00Z')).toBe('2026-10-17T14:23:00.000Z');
  });

  it('is unknown without a date, or with a broken one', () => {
    expect(unpaidDeadline(null)).toBe('');
    expect(unpaidDeadline(undefined)).toBe('');
    expect(unpaidDeadline('not a date')).toBe('');
  });

  it('a past-due business with its date says until when, never a fixed «7 more days»', () => {
    const late = { status: 'past_due', open_blocked_reason: null, unpaid_since: '2026-10-10T14:23:00Z' } as const;
    expect(reasonKey(late, false)).toBe('hubs.reason.pastDueUntil');
    expect(reasonKey(late, true)).toBe('hubs.reason.pastDueUntilApp');
    expect(reasonDate(late, 'es')).toBe('17 oct 2026');
    expect(reasonDate(late, 'en')).toBe('Oct 17, 2026');
  });

  it('a suspended business with its date says since when (the day, no time)', () => {
    const off = { status: 'suspended', open_blocked_reason: 'suspended', unpaid_since: '2026-10-09T08:00:00Z' } as const;
    expect(reasonKey(off, false)).toBe('hubs.reason.suspendedSince');
    expect(reasonKey(off, true)).toBe('hubs.reason.suspendedSinceApp');
    expect(reasonDate(off, 'es')).toBe('9 oct 2026');
  });

  it('a deleted business dates its recovery limit', () => {
    expect(reasonDate({ status: 'deleting', open_blocked_reason: 'deleting', purge_after: '2027-01-11T10:00:00Z' }, 'en')).toContain('Jan 11, 2027');
  });
});
