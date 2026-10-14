// «Pay» of an invoice Stripe could not charge (mockups `billing.html`; README §6.18 and §6.20; UX-AUDIT-4 R2):
// `billing.invoice.pay` answers Stripe's page for the invoice (its payer's card, 3-D Secure included) and the
// page goes there, a top-level navigation. One payment at a time on the page — whichever «Pay» started it,
// the banner's or the row's — until the page leaves: no double charge. The page remembers the invoice across
// Stripe's page (`sessionStorage`), so back here it can say «Invoice paid» for it (`unpaid.ts`). Back through
// the browser's cache (`pageshow` persisted), nothing is being paid any more.
import { toastError } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { inject, type InjectionKey, onScopeDispose, provide, readonly, shallowRef, type ShallowRef } from 'vue';

import { useErrorText } from '../../hubs/frontend/error-text';
import { browser } from './browser';

/** The invoice being paid on the page (its id), shared by every «Pay» under the page that provides it. */
const PAYING: InjectionKey<ShallowRef<string | null>> = Symbol('billing.paying');

/** Where the page remembers the invoice it went to pay at Stripe. */
export const PAYING_STORAGE_KEY = 'erplora.billing.paying';

/** The page's «one payment at a time» (BillingPage): every «Pay» below it shares it. */
export function providePaying(): ShallowRef<string | null> {
  const paying = shallowRef<string | null>(null);
  provide(PAYING, paying);
  return paying;
}

/** The invoice the page went to pay at Stripe, if any. */
export function rememberedPayment(): string | null {
  try {
    return window.sessionStorage.getItem(PAYING_STORAGE_KEY);
  } catch {
    return null; // Blocked storage: nothing remembered, nothing said.
  }
}

/** Forgets it once its outcome was said. */
export function forgetPayment(): void {
  try {
    window.sessionStorage.removeItem(PAYING_STORAGE_KEY);
  } catch {
    // Blocked storage: there is nothing to forget.
  }
}

function remember(id: string): void {
  try {
    window.sessionStorage.setItem(PAYING_STORAGE_KEY, id);
  } catch {
    // Blocked storage: the payment still goes; only «Invoice paid» after a reload is lost.
  }
}

export function usePayInvoice() {
  const paying = inject(PAYING, null) ?? shallowRef<string | null>(null);
  const command = useCommand('billing.invoice.pay');
  const { text } = useErrorText();

  const restored = (event: PageTransitionEvent) => {
    if (event.persisted) paying.value = null;
  };
  window.addEventListener('pageshow', restored);
  onScopeDispose(() => window.removeEventListener('pageshow', restored));

  /** Goes to Stripe's page for `invoice`; `false` when another payment is running or the server refused. */
  async function pay(invoice: { id: string }): Promise<boolean> {
    if (paying.value) return false;
    paying.value = invoice.id;
    try {
      const { url } = await command.run({ id: invoice.id });
      remember(invoice.id);
      browser.assign(url);
      return true;
    } catch {
      paying.value = null;
      void toastError(text(command.error.value));
      return false;
    }
  }

  return { pay, paying: readonly(paying) };
}
