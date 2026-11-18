// What the panel says of a discount, derived from its terms: in the Store once its code is checked, in the checkout
// next to the card, and on the subscription that carries it. English and Spanish, from billing's catalogues.
// clock: data only — the end of a discount is formatted, never compared with now.
import { describe, expect, it } from 'vitest';
import { createI18n } from 'vue-i18n';

import type { DiscountOut } from './discount-types';
import { carriedText, checkoutNotice, discountText, type Speak } from './discount-text';
import { formatCents, formatDate } from './format';
import en from './locale/en.json';
import es from './locale/es.json';

function speak(locale: 'en' | 'es'): Speak {
  const i18n = createI18n({ legacy: false, locale, messages: { en, es } });
  return { t: i18n.global.t, money: (cents) => formatCents(cents, locale) };
}

const PLANS = { kind: 'plans' as const, plans: [], intervals: ['month' as const] };

function discount(terms: Partial<DiscountOut>): DiscountOut {
  return {
    percent_off: 100,
    amount_off_cents: null,
    currency: 'eur',
    duration: 'repeating',
    duration_in_months: 6,
    applies_to: PLANS,
    ...terms,
  };
}

const FREE_6 = discount({});
const TWENTY_ONCE = discount({ percent_off: 20, duration: 'once', duration_in_months: null });
const TEN_FOREVER = discount({ percent_off: null, amount_off_cents: 1000, duration: 'forever', duration_in_months: null });

describe('discountText', () => {
  it.each([
    [FREE_6, 'Free for 6 months', 'Gratis durante 6 meses'],
    [discount({ duration_in_months: 1 }), 'Free for 1 month', 'Gratis durante 1 mes'],
    [TWENTY_ONCE, '20% off on the first payment', '20 % de descuento en el primer pago'],
    [TEN_FOREVER, '€10.00 off forever', '10,00 € de descuento para siempre'],
  ])('says what it takes off and for how long', (terms, english, spanish) => {
    expect(discountText(speak('en'), terms)).toBe(english);
    expect(discountText(speak('es'), terms)).toBe(spanish);
  });
});

describe('checkoutNotice', () => {
  const monthly = { cents: 2999, interval: 'month' as const };

  it('says when the plan’s price starts, and that nothing is charged today when the first payment is free', () => {
    expect(checkoutNotice(speak('en'), FREE_6, monthly)).toBe(
      'Free for 6 months. Then €29.99/month + VAT. Your card is not charged today.',
    );
    expect(checkoutNotice(speak('es'), FREE_6, monthly)).toBe(
      'Gratis durante 6 meses. Después, 29,99 €/mes + IVA. Hoy no se carga nada en tu tarjeta.',
    );
  });

  it('a discount on the first payment of a yearly plan', () => {
    expect(checkoutNotice(speak('en'), TWENTY_ONCE, { cents: 29_990, interval: 'year' })).toBe(
      '20% off on the first payment. Then €299.90/year + VAT.',
    );
  });

  it('a discount forever has no «then»; an amount at least the price charges nothing today', () => {
    expect(checkoutNotice(speak('en'), TEN_FOREVER, monthly)).toBe('€10.00 off forever.');
    expect(checkoutNotice(speak('en'), TEN_FOREVER, { cents: 900, interval: 'month' })).toBe(
      '€10.00 off forever. Your card is not charged today.',
    );
  });
});

describe('carriedText', () => {
  const day = (iso: string) => formatDate(iso, 'en');

  it('a discount for months says until when; one forever says so', () => {
    expect(carriedText(speak('en'), { code: 'testers', ends_at: '2027-05-16T10:00:00Z', terms: FREE_6 }, day)).toBe(
      'Free until May 16, 2027',
    );
    expect(carriedText(speak('es'), { code: 'ten', ends_at: null, terms: TEN_FOREVER }, day)).toBe(
      '10,00 € de descuento para siempre',
    );
  });
});
