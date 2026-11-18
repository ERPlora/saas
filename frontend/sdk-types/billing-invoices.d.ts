// The Billing section (billing/schemas/): ERPlora's invoices.

/** `billing.InvoicePaymentStatus`: not collected yet, paid, or cancelled in Stripe. */
export type InvoicePaymentStatus = 'open' | 'paid' | 'void';

/** `billing.InvoiceFiscalStatus`: what the platform hub says of it (`''` = not sent to it yet). */
export type InvoiceFiscalStatus = '' | 'issuing' | 'issued' | 'accepted' | 'accepted_with_errors' | 'rejected';

/** `billing.InvoiceRectificationType`: VeriFactu's `TipoFactura` of a rectifying invoice. */
export type InvoiceRectificationType = 'R1' | 'R2' | 'R3' | 'R4';

/** The actions of an invoice row (`billing.InvoiceRowOut.actions`), the fixed one first. */
export type InvoiceAction = 'pay' | 'pdf';

/** `billing.InvoiceFilterIn`: a business, the payment, a year and part of a number (all optional). */
export interface InvoiceFilterIn {
  hub_id?: string | null;
  status?: InvoicePaymentStatus | null;
  year?: number | null;
  search?: string | null;
}

/** `billing.InvoiceListIn`. */
export interface InvoiceListIn extends InvoiceFilterIn {
  limit?: number;
  offset?: number;
}

/** `billing.InvoiceBusinessOut`: `id` is null once the business is gone; its name stays as invoiced. */
export interface InvoiceBusinessOut {
  id: string | null;
  name: string;
}

/** `billing.InvoiceCanOut`: what the row's buttons do for this account. */
export interface InvoiceCanOut {
  pay: boolean;
  pdf: boolean;
}

/** `billing.InvoiceRectificationOut`: why a credit note rectifies (`reason` empty when Stripe gave none). */
export interface InvoiceRectificationOut {
  type: InvoiceRectificationType;
  reason: string;
}

/** `billing.InvoiceRowOut`: one invoice of ERPlora (amounts in cents). */
export interface InvoiceRowOut {
  id: string;
  kind: 'invoice' | 'credit_note';
  kind_label: string;
  /** `null` until it is paid: an unpaid one has only Stripe's `reference`. */
  number: string | null;
  reference: string;
  /** The day (`YYYY-MM-DD`). */
  date: string;
  business: InvoiceBusinessOut;
  currency: string;
  net_cents: number;
  tax_cents: number;
  total_cents: number;
  payment_status: InvoicePaymentStatus;
  payment_status_label: string;
  fiscal_status: InvoiceFiscalStatus;
  fiscal_status_label: string;
  /** Why «Pay» waits: a declined card to change first, or another account pays it. */
  pay_blocked_reason: 'card_change_required' | 'payer_required' | null;
  /** The row's actions in order, the fixed one first. */
  actions: InvoiceAction[];
  can: InvoiceCanOut;
  /** `null` for an invoice; a credit note's type (R1–R4) and reason. */
  rectification: InvoiceRectificationOut | null;
  /** The Stripe object behind a credit note (`cn_…`, `re_…`); `''` for an invoice. */
  stripe_source_id: string;
}

/** `billing.InvoiceListOut`. */
export interface InvoiceListOut {
  rows: InvoiceRowOut[];
  total: number;
  limit: number;
  offset: number;
}

/** `billing.InvoiceByIdIn`. */
export interface InvoiceByIdIn {
  id: string;
}

/** `billing.InvoiceLineOut`. */
export interface InvoiceLineOut {
  position: number;
  description: string;
  item_kind: 'plan' | 'module' | 'other';
  item_slug: string;
  quantity: number;
  proration: boolean;
  period_start: string | null;
  period_end: string | null;
  tax_rate: string;
  net_cents: number;
  tax_cents: number;
  total_cents: number;
  /** What a promo code took off the line, without VAT: `net_cents` is the base after it. */
  discount_cents: number;
}

/** `billing.InvoiceRecipientOut`: the payer as it was on the issue date. */
export interface InvoiceRecipientOut {
  name: string;
  tax_id: string;
  address: string;
  city: string;
  postal_code: string;
  country: string;
  email: string;
}

/** `billing.InvoiceRefOut`. */
export interface InvoiceRefOut {
  id: string;
  number: string;
}

/** `billing.InvoiceDetailOut`: the row, its lines, its recipient and its QR. */
export interface InvoiceDetailOut extends InvoiceRowOut {
  issued_on: string | null;
  paid_at: string | null;
  tax_treatment: string;
  tax_country: string;
  tax_rate: string;
  recipient: InvoiceRecipientOut;
  lines: InvoiceLineOut[];
  rectifies: InvoiceRefOut | null;
  qr: string;
}

/** `billing.InvoicePayIn`. */
export interface InvoicePayIn {
  id: string;
}

/** `billing.InvoicePayOut`: Stripe's page to pay it. */
export interface InvoicePayOut {
  url: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'billing.invoice.list': { input: InvoiceListIn | undefined; output: InvoiceListOut };
    'billing.invoice.get': { input: InvoiceByIdIn; output: InvoiceDetailOut };
    // A file (`Content-Disposition: attachment`): the browser downloads it (`billing/frontend/browser.ts`),
    // never `api.call`, which reads JSON.
    'billing.invoice.pdf': { input: InvoiceByIdIn; output: never };
    'billing.invoice.csv': { input: InvoiceFilterIn | undefined; output: never };
    'billing.invoice.pay': { input: InvoicePayIn; output: InvoicePayOut };
  }
}
