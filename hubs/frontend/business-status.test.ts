// How a business's status is painted everywhere (launcher, Businesses, its page): the ui's pill for the
// status, a danger pill when the Hub refused to prepare it, and the sentence that says why «Open» does
// not work (or what to do), which inside the apps never points at a payment page.
import { describe, expect, it } from 'vitest';

import { reasonKey, statusPill } from './business-status';

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
