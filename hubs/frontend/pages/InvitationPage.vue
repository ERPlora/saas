<script setup lang="ts">
// The invitation (`/invitation`, where the invitation email leads; `/invitations/:id` from the banners
// of the launcher and Businesses): mockups `invitation.html`, round 17 §2.8. A centred card, as the
// launcher, with every invitation waiting for the account's answer (the one asked for first): who
// invites and as what, «Accept and enter» (into the business at once) and «Decline» (confirmed). None
// waiting, or not the one asked for (expired after 7 days, already answered, sent to another email):
// «This invitation is no longer valid», with the panel and «Create my own business».
// Live data: `hubs.invitation.list_mine`.
import { InlineFeedback } from '@erplora/ui/components';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonSpinner, onIonViewWillEnter } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import type { InvitationOut } from '../../../frontend/sdk-types';
import CardShell from '../components/CardShell.vue';
import DeclineDialog from '../components/DeclineDialog.vue';
import { useAcceptInvitation } from '../invitations';

const props = defineProps<{
  /** The invitation asked for (a banner's link); every one without it (the email's link). */
  id?: string;
}>();

const { t } = useI18n();
const router = useRouter();
const session = useSession();
const live = useLive('hubs.invitation.list_mine', {});
const { accept, accepting } = useAcceptInvitation();

const declining = shallowRef<InvitationOut | null>(null);
const declineOpen = shallowRef(false);

const invitations = computed<InvitationOut[]>(() => {
  const all = live.data.value?.invitations ?? [];
  const asked = all.find((invitation) => invitation.id === props.id);
  return asked ? [asked, ...all.filter((invitation) => invitation !== asked)] : all;
});
const loaded = computed(() => !!live.data.value);
/** Nothing to answer, or the one asked for is not waiting any more. */
const expired = computed(
  () => loaded.value && (invitations.value.length === 0 || (!!props.id && invitations.value[0]?.id !== props.id)),
);
const email = computed(() => session.user.value?.email ?? '');

const title = computed(() => (expired.value ? t('hubs.invitation.expired.title') : t('hubs.invitation.pageTitle')));
const lead = computed(() => (expired.value ? t('hubs.invitation.expired.lead') : t('hubs.invitation.lead')));

function byLine(invitation: InvitationOut): string {
  return invitation.invited_by
    ? t('hubs.invitation.byLine', { inviter: invitation.invited_by, role: invitation.role_label })
    : invitation.role_label;
}

function decline(invitation: InvitationOut): void {
  declining.value = invitation;
  declineOpen.value = true;
}

/** The tab's name, each time the page comes on screen (Ionic reuses it). */
function entered(): void {
  document.title = `${t('hubs.invitation.pageTitle')} - ERPlora`;
}
onMounted(entered);
onIonViewWillEnter(entered);
</script>

<template>
  <CardShell
    icon="ion:mail-outline"
    :title="title"
    :lead="lead"
  >
    <!-- One stable element around the states: Ionic moves the dialog below out of the card while it
         is open, so Vue must never insert a state before it. -->
    <div class="card-body">
      <InlineFeedback
        v-if="live.status.value === 'error' && !loaded"
        tone="danger"
        data-testid="invitation-error"
      >
        {{ $t('hubs.invitation.loadError') }}
        <template #actions>
          <ion-button
            data-testid="invitation-retry"
            size="small"
            fill="outline"
            @click="live.refresh()"
          >
            <HubIcon
              slot="start"
              name="ion:refresh-outline"
            />
            {{ $t('hubs.common.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>

      <div
        v-else-if="!loaded"
        class="ion-text-center invite-loading"
        data-testid="invitation-loading"
      >
        <ion-spinner name="crescent" />
      </div>

      <div
        v-else-if="expired"
        class="ion-text-center"
        data-testid="invitation-expired"
      >
        <p class="card-text">
          {{ email ? $t('hubs.invitation.expired.body', { email }) : $t('hubs.invitation.expired.bodyNoEmail') }}
        </p>
        <ion-button
          data-testid="invitation-panel"
          expand="block"
          class="invite-main"
          @click="router.push('/businesses')"
        >
          <HubIcon
            slot="start"
            name="ion:storefront-outline"
          />
          {{ $t('hubs.common.goToPanel') }}
        </ion-button>
        <ion-button
          data-testid="invitation-create-own"
          class="link-button"
          expand="block"
          fill="clear"
          @click="router.push('/launch')"
        >
          <HubIcon
            slot="start"
            name="ion:add-outline"
          />
          {{ $t('hubs.invitation.expired.createOwn') }}
        </ion-button>
      </div>

      <template v-else>
        <div class="invite-list">
          <div
            v-for="invitation in invitations"
            :key="invitation.id"
            class="invite-card ion-padding"
            :data-testid="`invitation-${invitation.id}`"
          >
            <div class="invite-head">
              <HubIcon
                class="invite-icon"
                name="ion:storefront-outline"
              />
              <div class="invite-text">
                <h2>{{ invitation.hub.name }}</h2>
                <p class="invite-by">
                  {{ byLine(invitation) }}
                </p>
              </div>
            </div>
            <ion-button
              data-testid="invitation-accept"
              expand="block"
              :disabled="!!accepting"
              @click="accept(invitation)"
            >
              <ion-spinner
                v-if="accepting === invitation.id"
                slot="start"
                name="crescent"
                aria-hidden="true"
              />
              <HubIcon
                v-else
                slot="start"
                name="ion:log-in-outline"
              />
              {{ $t('hubs.invitation.accept') }}
            </ion-button>
            <ion-button
              data-testid="invitation-decline"
              expand="block"
              fill="clear"
              class="btn-neutral"
              :disabled="!!accepting"
              @click="decline(invitation)"
            >
              <HubIcon
                slot="start"
                name="ion:close-outline"
              />
              {{ $t('hubs.invitation.decline') }}
            </ion-button>
          </div>
        </div>
        <p
          class="shell-footnote ion-text-center"
          data-testid="invitation-foot"
        >
          {{ $t('hubs.invitation.foot') }}
        </p>
      </template>
    </div>

    <DeclineDialog
      v-model:open="declineOpen"
      :invitation="declining"
    />
  </CardShell>
</template>

<style scoped src="../components/buttons.css"></style>
<style scoped>
.card-text {
  margin: 0 0 16px;
  font-size: 0.9rem;
  line-height: 1.5;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.invite-loading {
  margin: 16px 0;
}
.invite-main {
  margin-top: 8px;
}
.invite-list {
  display: grid;
  gap: 12px;
}
.invite-card {
  border: 1px solid var(--ion-border-color);
  border-radius: 12px;
}
.invite-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
}
.invite-icon {
  flex: none;
  font-size: 22px;
  margin-top: 2px;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.invite-text {
  min-width: 0;
}
.invite-text h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 500;
  color: var(--ion-text-color);
}
.invite-by {
  margin: 2px 0 0;
  font-size: 0.8rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.invite-card ion-button {
  margin: 8px 0 0;
}
.btn-neutral {
  --color: var(--ion-text-color);
}
.shell-footnote {
  margin: 16px 0 0;
  font-size: 0.82rem;
  line-height: 1.5;
  color: color-mix(in oklab, var(--ion-text-color) 68%, transparent);
}
</style>
