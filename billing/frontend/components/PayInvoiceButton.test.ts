// «Pay the invoice» of an invoice Stripe could not charge (mockups `billing.html` «past-due» → «paying» →
// «paid»; README §6.18 and §6.20; UX-AUDIT-4 R2): `billing.invoice.pay` answers Stripe's page for it and
// the page goes there. One press pays once: from the press until the page leaves it says «Paying…» and
// every «Pay» of the page waits (no double charge). A card the bank declined, or another account paying
// the business, keeps it disabled with the reason next to it (`aria-describedby`). Back from Stripe
// through the browser's cache, nothing is being paid any more.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
}));

import { toastError } from '@erplora/ui/shell';

import { unpaidRow } from '../__tests__/billing-fixtures';
import { apiError, flush, mountBilling } from '../__tests__/mount-billing';
import { browser } from '../browser';
import { PAYING_STORAGE_KEY, providePaying } from '../pay';
import PayInvoiceButton from './PayInvoiceButton.vue';

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(toastError).mockClear();
  sessionStorage.clear();
  document.body.innerHTML = '';
});

/** An answer the test lets go when it wants: the press is «Paying…» meanwhile. */
function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((done) => (resolve = done));
  return { promise, resolve };
}

const button = (s: Awaited<ReturnType<typeof mountBilling>>, index = 0) => s.wrapper.findAll('[data-testid="pay-invoice"]')[index];

describe('PayInvoiceButton', () => {
  it('says what it pays, and goes to Stripe’s page for that invoice', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await mountBilling(PayInvoiceButton, {
      props: { invoice: unpaidRow('i1') },
      api: () => Response.json({ url: 'https://invoice.stripe.com/i/acct/i1' }),
    });
    expect(button(s).text()).toBe('Pay the invoice · €36.29');
    expect((button(s).element as HTMLButtonElement & { disabled: boolean }).disabled).toBe(false);
    await button(s).trigger('click');
    await flush();
    expect(s.calls()).toEqual([{ method: 'POST', path: '/api/billing/invoices/pay', body: { id: 'i1' }, query: {} }]);
    expect(assign).toHaveBeenCalledExactlyOnceWith('https://invoice.stripe.com/i/acct/i1');
    // Remembered across Stripe's page: back here, «Invoice paid» is said for it.
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBe('i1');
  });

  it('says «Paying…» from the press until the page leaves, and a second press charges nothing', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const answer = deferred();
    const s = await mountBilling(PayInvoiceButton, { props: { invoice: unpaidRow('i1') }, api: () => answer.promise });
    await button(s).trigger('click');
    await flush();
    expect(button(s).text()).toBe('Paying…');
    expect(button(s).find('ion-spinner').exists()).toBe(true);
    expect((button(s).element as HTMLButtonElement & { disabled: boolean }).disabled).toBe(true);
    await button(s).trigger('click');
    await flush();
    expect(s.calls()).toHaveLength(1);
    answer.resolve(Response.json({ url: 'https://invoice.stripe.com/i/acct/i1' }));
    await flush();
    expect(assign).toHaveBeenCalledTimes(1);
    expect(button(s).text()).toBe('Paying…');
  });

  it('one payment at a time on the page: while one «Pay» pays, the others wait', async () => {
    vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const answer = deferred();
    const Page = defineComponent({
      setup() {
        providePaying();
        return () => [h(PayInvoiceButton, { invoice: unpaidRow('i1') }), h(PayInvoiceButton, { invoice: unpaidRow('i2') })];
      },
    });
    const s = await mountBilling(Page, { api: () => answer.promise });
    await button(s, 0).trigger('click');
    await flush();
    expect(button(s, 0).text()).toBe('Paying…');
    expect((button(s, 1).element as HTMLButtonElement & { disabled: boolean }).disabled).toBe(true);
    await button(s, 1).trigger('click');
    await flush();
    expect(s.calls().map((call) => call.body)).toEqual([{ id: 'i1' }]);
  });

  it.each(['card_change_required', 'payer_required'] as const)('stays disabled when «Pay» waits (%s), described by the reason the page shows', async (reason) => {
    const s = await mountBilling(PayInvoiceButton, {
      props: { invoice: unpaidRow('i1', { pay_blocked_reason: reason, can: { pay: false, pdf: false } }), describedBy: 'why-i1' },
    });
    expect((button(s).element as HTMLButtonElement & { disabled: boolean }).disabled).toBe(true);
    // Ionic moves the host's `aria-*` onto its own native button, as in a browser.
    const host = button(s).element;
    expect(host.getAttribute('aria-describedby') ?? host.shadowRoot?.querySelector('button')?.getAttribute('aria-describedby')).toBe('why-i1');
    await button(s).trigger('click');
    await flush();
    expect(s.calls()).toEqual([]);
  });

  it('a refusal is said in a toast with the server’s words, and «Pay» is back', async () => {
    const assign = vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await mountBilling(PayInvoiceButton, {
      props: { invoice: unpaidRow('i1') },
      api: () => apiError(409, 'billing.invoice_paid', 'This invoice is paid already.'),
    });
    await button(s).trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('This invoice is paid already.');
    expect(assign).not.toHaveBeenCalled();
    expect(button(s).text()).toBe('Pay the invoice · €36.29');
    expect((button(s).element as HTMLButtonElement & { disabled: boolean }).disabled).toBe(false);
    expect(sessionStorage.getItem(PAYING_STORAGE_KEY)).toBeNull();
  });

  it('back from Stripe through the browser’s cache, nothing is being paid any more', async () => {
    vi.spyOn(browser, 'assign').mockImplementation(() => {});
    const s = await mountBilling(PayInvoiceButton, { props: { invoice: unpaidRow('i1') }, api: () => Response.json({ url: 'https://invoice.stripe.com/x' }) });
    await button(s).trigger('click');
    await flush();
    expect(button(s).text()).toBe('Paying…');
    window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    await flush();
    expect(button(s).text()).toBe('Pay the invoice · €36.29');
  });

  it('speaks Spanish', async () => {
    const s = await mountBilling(PayInvoiceButton, { props: { invoice: unpaidRow('i1') }, locale: 'es' });
    expect(button(s).text()).toBe('Pagar la factura · 36,29\u00a0€');
  });
});
