<script setup lang="ts">
// What waits above the businesses list for the account's answer: a notice per pending invitation («Accept» enters
// the business; «Decline» is handed to the page, which holds its confirmation) and per ownership offer, accepted or
// declined right here.
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

import type { InvitationOut, OwnershipOfferOut } from '../../../frontend/sdk-types/hubs';
import { useErrorText } from '../error-text';
import { useAcceptInvitation } from '../invitations';

defineProps<{ invitations: InvitationOut[]; offers: OwnershipOfferOut[] }>();
const emit = defineEmits<{ decline: [invitation: InvitationOut] }>();

const { t } = useI18n();
const { text } = useErrorText();
const { accept, accepting } = useAcceptInvitation();
const acceptOffer = useCommand('hubs.ownership.accept');
const declineOffer = useCommand('hubs.ownership.decline');

async function answerOffer(offer: OwnershipOfferOut, yes: boolean): Promise<void> {
  const command = yes ? acceptOffer : declineOffer;
  try {
    await command.run({ id: offer.id });
    toastSuccess(yes ? t('hubs.list.ownership.accepted', { name: offer.hub.name }) : t('hubs.list.ownership.declined'));
  } catch {
    toastError(text(command.error.value));
  }
}
</script>

<template>
  <InlineFeedback
    v-for="invitation in invitations"
    :key="invitation.id"
    tone="info"
    icon="ion:mail-outline"
    :data-testid="`businesses-invitation-${invitation.id}`"
    :heading="$t('hubs.list.invitation.heading', { name: invitation.hub.name })"
  >
    {{
      invitation.invited_by
        ? $t('hubs.list.invitation.body', { inviter: invitation.invited_by, role: invitation.role_label })
        : $t('hubs.list.invitation.bodyNoInviter', { role: invitation.role_label })
    }}
    <template #actions>
      <ion-button
        data-testid="invitation-accept"
        size="small"
        :disabled="!!accepting"
        @click="accept(invitation)"
      >
        <HubIcon
          slot="start"
          name="ion:checkmark-outline"
          aria-hidden="true"
        />
        {{ $t('hubs.invitation.accept') }}
      </ion-button>
      <ion-button
        data-testid="invitation-decline"
        size="small"
        fill="outline"
        class="btn-neutral"
        :disabled="!!accepting"
        @click="emit('decline', invitation)"
      >
        <HubIcon
          slot="start"
          name="ion:close-outline"
          aria-hidden="true"
        />
        {{ $t('hubs.invitation.decline') }}
      </ion-button>
    </template>
  </InlineFeedback>

  <InlineFeedback
    v-for="offer in offers"
    :key="offer.id"
    tone="info"
    icon="ion:swap-vertical-outline"
    :data-testid="`businesses-offer-${offer.id}`"
    :heading="$t('hubs.list.ownership.heading', { from: offer.from_email, name: offer.hub.name })"
  >
    {{ $t('hubs.list.ownership.body', { date: formatDateTime(offer.expires_at, $i18n.locale) }) }}
    <template #actions>
      <ion-button
        data-testid="offer-accept"
        size="small"
        :disabled="acceptOffer.pending.value || declineOffer.pending.value"
        @click="answerOffer(offer, true)"
      >
        <HubIcon
          slot="start"
          name="ion:checkmark-outline"
          aria-hidden="true"
        />
        {{ $t('hubs.list.ownership.accept') }}
      </ion-button>
      <ion-button
        data-testid="offer-decline"
        size="small"
        fill="outline"
        class="btn-neutral"
        :disabled="acceptOffer.pending.value || declineOffer.pending.value"
        @click="answerOffer(offer, false)"
      >
        <HubIcon
          slot="start"
          name="ion:close-outline"
          aria-hidden="true"
        />
        {{ $t('hubs.list.ownership.decline') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
.btn-neutral {
  --color: var(--ion-text-color);
  --border-color: color-mix(in oklab, var(--ion-text-color) 35%, transparent);
}
</style>
