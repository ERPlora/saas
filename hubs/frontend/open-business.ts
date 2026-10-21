// «Open»: the jump from the panel into a business (PLAN-SAAS §3.1 step 5). `hubs.business.open` checks
// the member and the business, remembers it as the last opened, and answers where the jump starts: the
// Hub's `/auth/login?next=`, which binds the jump to this browser with a `state` of its own and bounces
// to the SaaS's `/hub-login/`, the door that mints the code (and asks for the second factor of an
// account that has one). The page only goes there, a top-level navigation: no code ever passes through
// the SPA. A refusal (being prepared, suspended, deleted) is said in an error toast. Back from the Hub
// with the browser's back button the page may come from the cache (`pageshow` persisted): nothing is
// opening any more. Inside the installed app (the `desktop` and `mobile` surfaces, never the account it opens
// in the system browser) the jump carries `shell=1`: the app links the till to the business a navigation with
// that mark reaches when it leaves erplora.com (`ERPlora/app` hub_link.rs; PLAN-SAAS bloque 3).
import { toastError, useSurface } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { onScopeDispose, shallowRef } from 'vue';

import { useErrorText } from './error-text';

/** The browser's navigation, in one place (the tests watch it instead of leaving the page). */
export const navigation = {
  assign(url: string): void {
    window.location.assign(url);
  },
};

export function useOpenBusiness() {
  const command = useCommand('hubs.business.open');
  const { text } = useErrorText();
  const { surface } = useSurface();
  /** The business being opened (its id), until the page leaves; `null` otherwise. */
  const opening = shallowRef<string | null>(null);

  const restored = (event: PageTransitionEvent) => {
    if (event.persisted) opening.value = null;
  };
  window.addEventListener('pageshow', restored);
  onScopeDispose(() => window.removeEventListener('pageshow', restored));

  /** Opens `business` at `next` (its home by default); `false` when the server refused it. */
  async function open(business: { id: string; name: string }, next = '/'): Promise<boolean> {
    opening.value = business.id;
    try {
      const shell = surface.value === 'desktop' || surface.value === 'mobile';
      const { url } = await command.run(shell ? { id: business.id, next, shell } : { id: business.id, next });
      navigation.assign(url);
      return true;
    } catch {
      opening.value = null;
      void toastError(text(command.error.value));
      return false;
    }
  }

  return { open, opening, error: command.error };
}
