// «Pay» of an invoice Stripe could not charge: `billing.invoice.pay` answers Stripe's page for it and the page goes
// there, a top-level navigation. One payment at a time on the page until it leaves: no double charge. The invoice
// is remembered across Stripe's page (`sessionStorage`), so back here «Invoice paid» can be said for it.
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
