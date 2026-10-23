// Data of the Billing section's tests, shaped as billing/queries.py answers it: ERPlora's invoices
// (`billing.invoice.list`), the subscriptions (`billing.subscription.list`) and the payment method
// (`billing.payment_method.get`).
import type {
  InvoiceListOut,
  InvoiceRowOut,
  PaymentMethodOut,
  PaymentMethodRowOut,
  SubscriptionListOut,
  SubscriptionRowOut,
} from '../../../frontend/sdk-types';

export function invoiceRow(id: string, extra: Partial<InvoiceRowOut> = {}): InvoiceRowOut {
  return {
    id,
    kind: 'invoice',
    kind_label: 'Invoice',
    number: `ERP-2026-${id}`,
    reference: `REF-${id}`,
    date: '2026-10-01',
    business: { id: 'bakery', name: 'Panadería López' },
    currency: 'eur',
    net_cents: 2999,
    tax_cents: 630,
    total_cents: 3629,
    payment_status: 'paid',
    payment_status_label: 'Paid',
    fiscal_status: 'accepted',
    fiscal_status_label: 'Accepted',
    pay_blocked_reason: null,
    actions: ['pdf'],
    can: { pay: false, pdf: true },
    rectification: null,
    stripe_source_id: '',
    ...extra,
  };
}

/** An invoice Stripe could not charge: no number of ours yet, «Pay» first. */
export function unpaidRow(id: string, extra: Partial<InvoiceRowOut> = {}): InvoiceRowOut {
  return invoiceRow(id, {
    number: null,
    reference: `REF-${id}`,
    date: '2026-10-10',
    business: { id: 'plaza', name: 'Bar La Plaza' },
    payment_status: 'open',
    payment_status_label: 'Not collected',
    fiscal_status: '',
    fiscal_status_label: 'Not issued',
    actions: ['pay'],
    can: { pay: true, pdf: false },
    ...extra,
  });
}

export function invoicePage(rows: InvoiceRowOut[], extra: Partial<InvoiceListOut> = {}): InvoiceListOut {
  return { rows, total: rows.length, limit: 25, offset: 0, ...extra };
}

export function subscriptionRow(id: string, name: string, extra: Partial<SubscriptionRowOut> = {}): SubscriptionRowOut {
  return {
    business: { id, name },
    plan: { slug: 'starter', name: 'Starter', interval: 'month', price_cents: 2999 },
    modules: [],
    next_invoice: { date: '2026-11-01T00:00:00Z', total_cents: 3629, currency: 'EUR' },
    status: 'active',
    status_label: 'Active',
    cancelling: false,
    ends_at: null,
    cancel_requested: false,
    unpaid_invoice_id: null,
    scheduled_change: null,
    paid_by_another_account: false,
    actions: ['change_plan', 'cancel_plan', 'view_invoices'],
    can: { take_over: false, change_plan: true, cancel_plan: true, keep_plan: false, view_invoice: false, view_invoices: true },
    ...extra,
  };
}

export function subscriptionPage(rows: SubscriptionRowOut[]): SubscriptionListOut {
  return { rows, total: rows.length, limit: 50, offset: 0 };
}

export function paymentMethod(extra: Partial<PaymentMethodRowOut> = {}): PaymentMethodRowOut {
  return {
    businesses: [
      { id: 'bakery', name: 'Panadería López' },
      { id: 'plaza', name: 'Bar La Plaza' },
    ],
    card: { brand: 'visa', last4: '4242', exp_month: 8, exp_year: 2028 },
    unavailable: false,
    last_failure: null,
    ...extra,
  };
}

export function paymentMethods(methods: PaymentMethodRowOut[] = [paymentMethod()]): PaymentMethodOut {
  return { methods };
}
