// The Store's rules, apart from the screen (round 17 §2.9–§2.11; mockups `store.html`, README §6.18 and
// UX-AUDIT-4: «the block for an unpaid invoice goes by business»):
//   - a module is sold when the catalog lists its app as premium AND billing has it on sale (`apps.Module`),
//     joined by `slug == app.id`: name, summary and icon from the catalog, prices from billing;
//   - only the owner buys for a business, and a deleted one buys nothing;
//   - a business with an unpaid invoice buys nothing more until it pays it, and says why;
//   - a module follows the business's billing; a free business buys it monthly.
import { describe, expect, it } from 'vitest';

import { APPS, app, BAKERY, CAFE, PLAZA, SALON, STARTER, FREE, businessRow, plan, storeModule, subscription, FREE_SUBSCRIPTION } from './__tests__/fixtures';
import { annualSaving, blockOf, declinedCard, isFree, moduleInterval, ownedBusinesses, saleModules } from './store';

describe('saleModules', () => {
  it('sells the premium apps billing has on sale: name, summary and icon of one, prices of the other', () => {
    const modules = saleModules(APPS.apps, [storeModule('loyalty', 600), storeModule('booking', 900, { owned: true, source: 'purchase' })]);
    expect(modules).toEqual([
      {
        slug: 'booking',
        name: 'Bookings',
        summary: 'Calendar, online bookings and reminders.',
        iconSvg: APPS.apps[0].icon_svg,
        priceMonthlyCents: 900,
        priceAnnualCents: 9000,
        owned: true,
        source: 'purchase',
        validUntil: null,
      },
      {
        slug: 'loyalty',
        name: 'Loyalty',
        summary: 'Points, cards and discounts for customers.',
        iconSvg: APPS.apps[1].icon_svg,
        priceMonthlyCents: 600,
        priceAnnualCents: 6000,
        owned: false,
        source: null,
        validUntil: null,
      },
    ]);
  });

  it('does not sell an app that is not premium, nor a premium app billing has not on sale', () => {
    const modules = saleModules([...APPS.apps, app('kitchen', 'Kitchen')], [storeModule('sales', 500), storeModule('booking', 900)]);
    expect(modules.map((module) => module.slug)).toEqual(['booking']);
  });

  it('does not sell a module whose app the catalog no longer lists (nothing to name it with)', () => {
    expect(saleModules(APPS.apps, [storeModule('retired', 500)])).toEqual([]);
  });

  it('keeps the catalog’s order (by section, then by name in the language)', () => {
    const modules = saleModules([app('zeta', 'Zeta'), app('alpha', 'Alpha')], [storeModule('alpha', 100), storeModule('zeta', 100)]);
    expect(modules.map((module) => module.slug)).toEqual(['zeta', 'alpha']);
  });
});

describe('ownedBusinesses', () => {
  it('keeps the businesses the account owns and that are not deleted', () => {
    const deleted = businessRow('gone', 'Gone', { status: 'deleting' });
    expect(ownedBusinesses([BAKERY, SALON, CAFE, deleted]).map((row) => row.id)).toEqual(['bakery', 'cafe']);
  });
});

describe('blockOf', () => {
  it('a paid business buys freely', () => {
    expect(blockOf(BAKERY)).toBeNull();
  });

  it('an unpaid invoice blocks, saying whether the card was declined or changed', () => {
    expect(blockOf(PLAZA)).toBe('card_declined');
    expect(blockOf({ ...PLAZA, unpaid_reason: 'card_changed' })).toBe('card_changed');
    expect(blockOf({ ...PLAZA, unpaid_reason: 'payment_failed' })).toBe('unpaid');
  });

  it('a payment pending or a suspension blocks even before the reason arrives', () => {
    expect(blockOf({ ...BAKERY, status: 'past_due' })).toBe('unpaid');
    expect(blockOf({ ...BAKERY, status: 'suspended' })).toBe('unpaid');
  });
});

describe('declinedCard', () => {
  it('names the business whose card was declined when it has the same payer as the one being sold to', () => {
    const shared = { ...CAFE, payer_id: PLAZA.payer_id };
    expect(declinedCard([BAKERY, PLAZA, shared], shared)).toBe('Bar La Plaza');
    expect(declinedCard([BAKERY, { ...PLAZA, is_payer: false, payer_id: null }, shared], shared)).toBeNull();
  });

  it('another payer’s declined card is not this business’s (audit 2 R-21: each business has its own payer)', () => {
    expect(declinedCard([BAKERY, PLAZA, CAFE], CAFE)).toBeNull();
    expect(declinedCard([BAKERY, CAFE], CAFE)).toBeNull();
  });
});

describe('isFree', () => {
  it('a plan without a monthly price is Free', () => {
    expect(isFree(FREE)).toBe(true);
    expect(isFree(STARTER)).toBe(false);
  });
});

describe('annualSaving', () => {
  it('says the largest saving of paying a year, in whole percent', () => {
    // 29.99 × 12 = 359.88 against 299.90: 16.7 % → 17 %.
    expect(annualSaving([FREE, STARTER])).toBe(17);
    expect(annualSaving([FREE, STARTER, plan('pro', 'Pro', '50.00', '500.00')])).toBe(17);
  });

  it('no saving without a paid plan', () => {
    expect(annualSaving([FREE])).toBe(0);
  });
});

describe('moduleInterval', () => {
  it('a module follows the billing of a business that pays; a free one buys it monthly', () => {
    expect(moduleInterval(subscription({ billing_interval: 'year' }))).toBe('year');
    expect(moduleInterval(FREE_SUBSCRIPTION)).toBe('month');
    expect(moduleInterval(null)).toBe('month');
  });
});
