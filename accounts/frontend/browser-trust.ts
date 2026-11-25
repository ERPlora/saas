// «Trusted browsers» of the two-factor settings (ACCOUNTS-F17): whether this browser skips the app's code (ACCOUNTS-F05)
// and until when (`accounts.browser_trust.get`; allauth keeps no list, so only this one can be told), and «Stop trusting
// all browsers» (`accounts.browser_trust.revoke`). Read apart from the authenticators: it never holds the page.
import type { LiveClient } from '@erplora/ui/sdk';
import { shallowRef } from 'vue';

export function useBrowserTrust(client: Pick<LiveClient, 'api'>) {
  /** Until when this browser is trusted: a date, `null` (not trusted), `undefined` (not known yet, or not readable). */
  const trustedUntil = shallowRef<string | null | undefined>(undefined);
  const trustUnknown = shallowRef(false);
  /** «Stop trusting all browsers» went through. */
  const trustRevoked = shallowRef(false);

  /** Whether this browser is trusted, and until when; read on its own, it never holds the page. */
  async function loadTrust(): Promise<void> {
    trustUnknown.value = false;
    try {
      trustedUntil.value = (await client.api.call('accounts.browser_trust.get')).trusted_until;
    } catch {
      trustedUntil.value = undefined;
      trustUnknown.value = true;
    }
  }

  /** «Stop trusting all browsers»; a failure is thrown for the page to show. */
  async function revokeTrust(): Promise<void> {
    trustedUntil.value = (await client.api.call('accounts.browser_trust.revoke')).trusted_until;
    trustUnknown.value = false;
    trustRevoked.value = true;
  }

  return { trustedUntil, trustUnknown, trustRevoked, loadTrust, revokeTrust };
}
