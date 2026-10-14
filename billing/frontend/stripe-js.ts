// Stripe.js for the Embedded Checkout (PLAN-SAAS §3.6 point 17; plan §7 point 5). The one script the SaaS
// takes from another origin — PCI: Stripe.js is never served by us — loaded only when a payment opens,
// and only on the web: the apps and the account surface sell nothing (round 17 §2.6), so off the web it
// refuses before touching the page.
//   - Our code inserts it (CSP `'strict-dynamic'` trusts what a nonced script inserts) and gives it the
//     page's nonce as well, for a browser without `'strict-dynamic'`.
//   - Production enforces Trusted Types (`require-trusted-types-for 'script'`): a script's address is a
//     sink. Its address is a plain string, as Stripe.js's own loader sets its chunks: the page's
//     `default` policy admits the script URLs of `https://js.stripe.com` and no other origin
//     (`createShell({ trustedScriptOrigins })`, frontend/main.ts). One mechanism, no policy of ours.
import { useSurface } from '@erplora/ui/shell';

/** Stripe.js v3. */
export const STRIPE_JS_URL = 'https://js.stripe.com/v3/';

/** What the Store uses of Stripe.js: the Embedded Checkout, mounted from a Checkout Session's secret. */
export interface EmbeddedCheckout {
  mount(target: Element | string): void;
  destroy(): void;
}
export interface StripeInstance {
  createEmbeddedCheckoutPage(options: {
    fetchClientSecret: () => Promise<string>;
    onComplete?: () => void;
  }): Promise<EmbeddedCheckout>;
}
export type StripeFactory = (publishableKey: string) => StripeInstance;

type StripeWindow = Window & { Stripe?: StripeFactory };

let loading: Promise<StripeFactory> | null = null;

/**
 * Stripe.js's `Stripe`, loading it the first time. A failure rejects (and the next call tries again);
 * off the web it rejects without loading anything.
 */
export function loadStripeJs({ doc = document, win = window }: { doc?: Document; win?: Window } = {}): Promise<StripeFactory> {
  if (!useSurface().isWeb.value) return Promise.reject(new Error('Stripe.js is web only: the apps sell nothing'));
  const stripeWindow = win as StripeWindow;
  if (stripeWindow.Stripe) return Promise.resolve(stripeWindow.Stripe);
  if (loading) return loading;
  const attempt = new Promise<StripeFactory>((resolve, reject) => {
    const script = doc.createElement('script');
    script.async = true;
    const nonce = doc.querySelector<HTMLScriptElement>('script[nonce]')?.nonce;
    if (nonce) script.nonce = nonce;
    script.onload = () => {
      if (stripeWindow.Stripe) resolve(stripeWindow.Stripe);
      else reject(new Error('Stripe.js loaded without Stripe'));
    };
    script.onerror = () => reject(new Error('Stripe.js could not be loaded'));
    script.src = STRIPE_JS_URL;
    doc.head.append(script);
  });
  loading = attempt;
  attempt.catch(() => {
    if (loading === attempt) loading = null;
  });
  return attempt;
}

/** Forgets a load in flight (tests). */
export function resetStripeJs(): void {
  loading = null;
}
