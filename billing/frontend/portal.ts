// «Change card» (mockups `billing.html`; README §6.18): Stripe's Customer Portal for the payer of a business
// (`billing.portal.open`: cards and Stripe's receipts; the plan changes in the panel, which puts our own
// tax rates), a top-level navigation that comes back to Billing. Web only: the pages render it in
// `<WebOnly>`. One opening at a time (the business being opened); back through the browser's cache
// (`pageshow` persisted), nothing is opening any more. A refusal is said in a toast.
import { toastError } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { onScopeDispose, readonly, shallowRef } from 'vue';

import { useErrorText } from '../../hubs/frontend/error-text';
import { browser } from './browser';

export function useCardPortal() {
  const command = useCommand('billing.portal.open');
  const { text } = useErrorText();
  /** The business whose payer's Portal is being opened, until the page leaves. */
  const opening = shallowRef<string | null>(null);

  const restored = (event: PageTransitionEvent) => {
    if (event.persisted) opening.value = null;
  };
  window.addEventListener('pageshow', restored);
  onScopeDispose(() => window.removeEventListener('pageshow', restored));

  /** Goes to the Portal of `hubId`'s payer; `false` when one is opening already or the server refused. */
  async function open(hubId: string): Promise<boolean> {
    if (opening.value) return false;
    opening.value = hubId;
    try {
      const { url } = await command.run({ hub_id: hubId });
      browser.assign(url);
      return true;
    } catch {
      opening.value = null;
      void toastError(text(command.error.value));
      return false;
    }
  }

  return { open, opening: readonly(opening) };
}
