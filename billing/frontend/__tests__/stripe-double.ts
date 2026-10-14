// A stand-in for Stripe.js (`window.Stripe`) in the Store's tests: the Embedded Checkout cannot run
// without Stripe, so the double records the publishable key, the client secret the page hands over, the
// container it mounts into, and lets a test complete the payment (`complete()`) or fail the mount.
export interface EmbeddedCheckoutDouble {
  mountedOn: Element | string | null;
  destroyed: boolean;
  mount(target: Element | string): void;
  destroy(): void;
}

export interface StripeDouble {
  keys: string[];
  secrets: string[];
  checkouts: EmbeddedCheckoutDouble[];
  /** Runs the `onComplete` of the last checkout, as Stripe does once the payment succeeds. */
  complete(): void;
  /** The next `createEmbeddedCheckoutPage` rejects with this error. */
  failNext(error: Error): void;
  factory: (key: string) => unknown;
}

export function stripeDouble(): StripeDouble {
  let onComplete: (() => void) | undefined;
  let failure: Error | null = null;
  const double: StripeDouble = {
    keys: [],
    secrets: [],
    checkouts: [],
    complete: () => onComplete?.(),
    failNext: (error) => void (failure = error),
    factory: (key: string) => {
      double.keys.push(key);
      return {
        async createEmbeddedCheckoutPage(options: { fetchClientSecret: () => Promise<string>; onComplete?: () => void }) {
          if (failure) {
            const error = failure;
            failure = null;
            throw error;
          }
          double.secrets.push(await options.fetchClientSecret());
          onComplete = options.onComplete;
          const checkout: EmbeddedCheckoutDouble = {
            mountedOn: null,
            destroyed: false,
            mount(target) {
              checkout.mountedOn = target;
            },
            destroy() {
              checkout.destroyed = true;
            },
          };
          double.checkouts.push(checkout);
          return checkout;
        },
      };
    },
  };
  return double;
}
