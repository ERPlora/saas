// «Accept and enter» an invitation (round 17 §2.8): `hubs.invitation.accept` gives the business as the
// list shows it; then straight into it when it opens, or to Businesses when it does not open yet
// (being prepared, suspended), where its row says why. A refusal (expired, already answered) is said in
// an error toast.
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { BUSINESSES } from '../../accounts/frontend/paths';
import type { InvitationOut } from '../../frontend/sdk-types';
import { useErrorText } from './error-text';
import { useOpenBusiness } from './open-business';

export function useAcceptInvitation() {
  const { t } = useI18n();
  const router = useRouter();
  const command = useCommand('hubs.invitation.accept');
  const { open } = useOpenBusiness();
  const { text } = useErrorText();
  /** The invitation being accepted (its id), until the page leaves for the business. */
  const accepting = shallowRef<string | null>(null);

  async function accept(invitation: InvitationOut): Promise<void> {
    accepting.value = invitation.id;
    let business;
    try {
      business = await command.run({ id: invitation.id });
    } catch {
      accepting.value = null;
      void toastError(text(command.error.value));
      return;
    }
    void toastSuccess(t('hubs.invitation.accepted', { name: business.name }));
    if (business.can_open && (await open(business))) return;
    accepting.value = null;
    await router.push(BUSINESSES);
  }

  return { accept, accepting, error: command.error };
}
