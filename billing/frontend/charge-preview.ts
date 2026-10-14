// What confirming a change charges NOW, before the owner confirms it (PLAN-SAAS §3.2): for a business
// Stripe bills already, `billing.checkout.start` answers `flow: "confirm"` with Stripe's prorated
// preview — the amount with VAT, the VAT, and the proration date the confirmation sends back so the
// charge is the preview's to the cent. A business that does not pay yet answers `flow: "checkout"`
// (`state: 'checkout'`): the Store opens the Embedded Checkout instead.
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { computed, shallowRef } from 'vue';

import type { ChargePreviewOut, CheckoutStartIn } from '../../frontend/sdk-types';

export type ChargePreviewState = 'idle' | 'loading' | 'ready' | 'checkout' | 'error';

export function useChargePreview() {
  const start = useCommand('billing.checkout.start');
  const state = shallowRef<ChargePreviewState>('idle');
  const preview = shallowRef<ChargePreviewOut | null>(null);
  const error = shallowRef<ApiError | null>(null);
  /** The charge without its VAT. */
  const netCents = computed(() => (preview.value ? preview.value.amount_due_cents - preview.value.tax_cents : 0));

  async function load(input: CheckoutStartIn): Promise<void> {
    state.value = 'loading';
    preview.value = null;
    error.value = null;
    try {
      const answer = await start.run(input);
      preview.value = answer.preview;
      state.value = answer.flow === 'confirm' && answer.preview ? 'ready' : 'checkout';
    } catch {
      error.value = start.error.value;
      state.value = 'error';
    }
  }

  return { state, preview, error, netCents, load };
}
