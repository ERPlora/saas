<script setup lang="ts">
// The entry of erplora.com and of the apps (`/launch`; Django's old `/launch/` redirects here). A centred card
// without the menu
// (`meta.chrome: false`) that never enters a business by itself unless the person just created it or
// is waiting for the only one to be ready:
//   - signed out → the sign-in itself: the one form that signs in and creates the account
//     (`SignInForm`), in the frame of the old template login (`AuthShell`), then the code mailed to the
//     account; signed in, the page loads again with the new session (or `next`). Signed in with a `next` of
//     this site (Django's `LOGIN_URL` keeps it), it goes there at once, as the template login did;
//   - no business → the sign-up form, «or», «Go to the panel»; with a pending invitation the card IS
//     the invitation (accept and enter, decline, or create one's own); after creating, «Preparing»
//     and it opens by itself when the Hub reports it ready (or says it could not be prepared);
//   - one business → «Open X» (disabled while it is prepared, gone while suspended) and «Go to the
//     panel», with why it does not open;
//   - several → the server's order (the last opened first), «Open» on each, «Create another business».
// Live data: `hubs.business.list` (the account's businesses and its pending invitations), its states truthful
// (`useLiveState`: no answer in time is an error with «Retry», never a spinner for ever).
// Ionic reuses the page when it comes back on screen: its address (`?notice=`) and the tab's title are read then.
import { InlineFeedback } from '@erplora/ui/components';
import AuthShell from '../../../accounts/frontend/components/AuthShell.vue';
import SignInForm from '../../../accounts/frontend/components/SignInForm.vue';
import { legalHref } from '../../../accounts/frontend/legal';
import { localNext } from '../../../accounts/frontend/next';
import { BUSINESSES, LAUNCHER } from '../../../accounts/frontend/paths';
import { HubIcon, useSession, useSurface } from '@erplora/ui/shell';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonSpinner, onIonViewWillEnter } from '@ionic/vue';
import { computed, onMounted, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { useLiveState } from '../../../frontend/live-state';
import LoadFailed from '../../../frontend/LoadFailed.vue';
import type { BusinessRowOut, InvitationOut } from '../../../frontend/sdk-types/hubs';
import { preparationFailed, preparingLeadKey } from '../business-status';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';
import BusinessPreparing from '../components/BusinessPreparing.vue';
import CardShell from '../components/CardShell.vue';
import DeclineDialog from '../components/DeclineDialog.vue';
import LaunchBusinesses from '../components/LaunchBusinesses.vue';
import LaunchInvitation from '../components/LaunchInvitation.vue';
import { useAcceptInvitation } from '../invitations';
import { useOpenBusiness } from '../open-business';

const { t } = useI18n();
const router = useRouter();
const session = useSession();
const { surface } = useSurface();

const user = computed(() => session.user.value);
// Signed in already with somewhere to go (a path of this site other than this page): there at once.
const next = localNext(router.currentRoute.value.query.next);
if (user.value && next && next.split(/[?#]/)[0] !== LAUNCHER) location.assign(next);
const mfaUnavailable = shallowRef(false);
// Signed out there is nothing to follow (and the stream would refuse it): only then no subscription.
// Signing in or out reloads the page (allauth.headless's session, then a full page load: the sign-out is
// `DELETE /_allauth/browser/v1/auth/session`, `CardShell.vue` and `frontend/main.ts`), so this is decided once.
const live = user.value ? useLive('hubs.business.list', { limit: 50, offset: 0 }) : null;
const state = live ? useLiveState(live) : null;
const { open, opening } = useOpenBusiness();
const { accept, accepting } = useAcceptInvitation();

/** The business just created here: its preparation is shown until it opens. */
const created = shallowRef<{ id: string; name: string; typeName: string | null } | null>(null);
/** Invited, the person chose to create a business of their own instead. */
const ownForm = shallowRef(false);
const declining = shallowRef<InvitationOut | null>(null);
const declineOpen = shallowRef(false);

const rows = computed<BusinessRowOut[]>(() => live?.data.value?.rows ?? []);
const invitations = computed<InvitationOut[]>(() => live?.data.value?.invitations ?? []);

type Variant = 'signedOut' | 'loading' | 'error' | 'preparing' | 'failed' | 'invited' | 'first' | 'one' | 'several';
/** The business just created, as the live list has it (not there yet right after creating it). */
const createdRow = computed(() => rows.value.find((row) => row.id === created.value?.id));
const variant = computed<Variant>(() => {
  if (!live) return 'signedOut';
  if (!live.data.value) return state?.failed.value ? 'error' : 'loading';
  if (created.value) return createdRow.value && preparationFailed(createdRow.value) ? 'failed' : 'preparing';
  if (rows.value.length === 0) return invitations.value.length && !ownForm.value ? 'invited' : 'first';
  return rows.value.length === 1 ? 'one' : 'several';
});

const firstName = computed(() => {
  const label = user.value?.label?.trim() ?? '';
  return label && !label.includes('@') ? label.split(/\s+/)[0] : '';
});
const invitation = computed(() => invitations.value[0] ?? null);

const title = computed(() => {
  switch (variant.value) {
    case 'preparing':
      return t('hubs.launch.preparing.title', { name: created.value?.name ?? '' });
    case 'failed':
      return t('hubs.createModal.errorTitle');
    case 'invited':
      return t('hubs.launch.invited.title', { name: invitation.value?.hub.name ?? '' });
    case 'first':
      return t('hubs.launch.first.title');
    case 'several':
      return t('hubs.launch.several.title');
    default:
      return firstName.value ? t('hubs.launch.one.greeting', { name: firstName.value }) : t('hubs.launch.one.greetingNoName');
  }
});

const lead = computed(() => {
  switch (variant.value) {
    case 'preparing': {
      const key = preparingLeadKey(createdRow.value?.maintenance);
      return key ? t(key) : '';
    }
    case 'invited':
      return ''; // the `#lead` slot: the role in bold.
    case 'first':
      return t('hubs.launch.first.lead');
    case 'several':
      return t('hubs.launch.several.lead');
    case 'one':
      return t('hubs.launch.one.lead');
    default:
      return '';
  }
});

const icon = computed(() => {
  switch (variant.value) {
    case 'invited':
      return 'ion:mail-outline';
    case 'failed':
      return 'ion:warning-outline';
    case 'one':
      return 'ion:person-circle-outline';
    default:
      return 'ion:storefront-outline';
  }
});

// ── Opening by itself ─────────────────────────────────────────────────────────────────────────
// A business seen being prepared during this visit opens when it is ready, if it is the one just
// created here or the only one: with several, the person chooses. It stays awaited until it really
// opens, so an opening the server refused is tried again with the business's next news.
const waiting = new Set<string>();
watch(
  rows,
  (now) => {
    for (const business of now) {
      if (business.status === 'preparing' && !business.can_open) {
        waiting.add(business.id);
        continue;
      }
      const mine = created.value?.id === business.id || now.length === 1;
      if (business.can_open && waiting.has(business.id) && mine && !opening.value) {
        void open(business).then((opened) => {
          if (opened) waiting.clear();
        });
      }
    }
  },
  { immediate: true },
);

function onCreated(business: { id: string; name: string }, extra: { typeName: string | null }): void {
  created.value = { id: business.id, name: business.name, typeName: extra.typeName };
  waiting.add(business.id);
}

function decline(it: InvitationOut): void {
  declining.value = it;
  declineOpen.value = true;
}

const toPanel = () => router.push(BUSINESSES);

/** Each time the page comes on screen (Ionic reuses it): what its address says, and the tab's name. */
function entered(): void {
  mfaUnavailable.value = router.currentRoute.value.query.notice === 'mfa_unavailable';
  // Signed out the page is the template login, and the tab says so.
  document.title = variant.value === 'signedOut' ? `${t('accounts.login.title')} - ERPlora Cloud` : `${t('hubs.launch.pageTitle')} - ERPlora`;
}
onMounted(entered);
onIonViewWillEnter(entered);
</script>

<template>
  <AuthShell
    v-if="variant === 'signedOut'"
    :subtitle="$t('accounts.login.subtitle')"
  >
    <SignInForm />
    <template #foot>
      <p class="foot">
        {{ $t('accounts.login.agree') }}
        <a :href="legalHref('terms', surface)">{{ $t('accounts.login.terms') }}</a>
        &amp;
        <a :href="legalHref('privacy', surface)">{{ $t('accounts.login.privacy') }}</a>.
      </p>
    </template>
  </AuthShell>
  <CardShell
    v-else
    :icon="icon"
    :title="title"
    :lead="lead"
  >
    <template
      v-if="variant === 'invited' && invitation"
      #lead
    >
      <i18n-t :keypath="invitation.invited_by ? 'hubs.launch.invited.lead' : 'hubs.launch.invited.leadNoInviter'">
        <template #inviter>
          {{ invitation.invited_by }}
        </template>
        <template #role>
          <strong>{{ invitation.role_label }}</strong>
        </template>
      </i18n-t>
    </template>
    <!-- One stable element around the states: Ionic moves the dialog below out of the card while it
         is open, so Vue must never insert a state before it. -->
    <div class="card-body">
      <InlineFeedback
        v-if="mfaUnavailable"
        tone="info"
        class="launch-notice"
        data-testid="launch-notice"
      >
        {{ $t('hubs.launch.mfaUnavailable') }}
      </InlineFeedback>

      <!-- ═══ Loading and error ═══ -->
      <div
        v-if="variant === 'loading'"
        class="ion-text-center launch-loading"
        data-testid="launch-loading"
      >
        <ion-spinner name="crescent" />
      </div>

      <LoadFailed
        v-else-if="variant === 'error'"
        :heading="$t('hubs.launch.loadError')"
        testid="launch-error"
        retry-testid="launch-retry"
        @retry="state?.retry()"
      />

      <!-- ═══ Just created: preparing ═══ -->
      <template v-else-if="variant === 'preparing' && created">
        <BusinessPreparing
          :id="created.id"
          :name="created.name"
          :type-name="created.typeName"
          :maintenance="createdRow?.maintenance ?? null"
          last="opensAlone"
        />
        <ion-button
          data-testid="launch-panel"
          expand="block"
          fill="outline"
          class="ion-margin-top"
          @click="toPanel"
        >
          <HubIcon
            slot="start"
            name="ion:grid-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.launch.preparing.meanwhile') }}
        </ion-button>
      </template>

      <!-- ═══ Just created, and the Hub could not prepare it ═══ -->
      <template v-else-if="variant === 'failed' && created">
        <InlineFeedback
          tone="danger"
          data-testid="launch-failed"
        >
          {{ $t('hubs.createModal.error', { name: created.name }) }}
        </InlineFeedback>
        <ion-button
          data-testid="launch-panel"
          expand="block"
          class="launch-main"
          @click="toPanel"
        >
          <HubIcon
            slot="start"
            name="ion:grid-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.common.goToPanel') }}
        </ion-button>
      </template>

      <!-- ═══ Invited, without a business of one's own: the card is the invitation ═══ -->
      <LaunchInvitation
        v-else-if="variant === 'invited' && invitation"
        :invitation="invitation"
        :accepting="accepting"
        @accept="accept"
        @decline="decline"
        @create-own="ownForm = true"
      />

      <!-- ═══ First time: create the business here ═══ -->
      <template v-else-if="variant === 'first'">
        <BusinessCreateForm @created="onCreated" />
        <div
          class="launch-divider"
          data-testid="launch-divider"
        >
          <span>{{ $t('hubs.launch.first.or') }}</span>
        </div>
        <ion-button
          data-testid="launch-panel"
          expand="block"
          fill="outline"
          @click="toPanel"
        >
          <HubIcon
            slot="start"
            name="ion:grid-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.common.goToPanel') }}
        </ion-button>
        <p
          class="shell-footnote ion-text-center"
          data-testid="launch-foot"
        >
          {{ $t('hubs.launch.first.invited') }}
        </p>
      </template>

      <!-- ═══ One business or several ═══ -->
      <template v-else-if="variant === 'one' || variant === 'several'">
        <InlineFeedback
          v-if="invitation"
          tone="info"
          icon="ion:mail-outline"
          class="launch-notice"
          data-testid="launch-invitation"
          :heading="$t('hubs.launch.invitationBanner.heading', { name: invitation.hub.name })"
        >
          <template #actions>
            <ion-button
              data-testid="launch-invitation-open"
              size="small"
              fill="outline"
              @click="router.push(`/invitations/${invitation.id}`)"
            >
              {{ $t('hubs.launch.invitationBanner.action') }}
            </ion-button>
          </template>
        </InlineFeedback>

        <LaunchBusinesses
          :rows="rows"
          :opening="opening"
          @open="open"
        />

        <ion-button
          data-testid="launch-panel"
          expand="block"
          fill="outline"
          class="ion-margin-top"
          @click="toPanel"
        >
          <HubIcon
            slot="start"
            name="ion:grid-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.common.goToPanel') }}
        </ion-button>
        <ion-button
          v-if="variant === 'several'"
          data-testid="launch-create-another"
          class="link-button"
          expand="block"
          fill="clear"
          @click="router.push({ path: BUSINESSES, query: { create: '1' } })"
        >
          <HubIcon
            slot="start"
            name="ion:add-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.launch.several.createAnother') }}
        </ion-button>
        <p
          v-else
          class="shell-footnote ion-text-center"
          data-testid="launch-foot"
        >
          {{ $t('hubs.launch.one.foot') }}
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
/* The terms under the sign-in's card, as `templates/account/_auth_styles.html` had them. */
.foot {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  color: color-mix(in oklch, var(--ion-text-color) 45%, transparent);
  text-align: center;
}
.foot a {
  color: var(--ion-color-primary);
}
.foot a:hover {
  text-decoration: underline;
}
/* `mock.css` of the mockups (launch-*), with our tokens. */
.launch-main {
  margin-top: 16px;
}
ion-button[expand='block'] + ion-button[expand='block'] {
  margin-top: 10px;
}
.launch-notice {
  margin-bottom: 14px;
}
.launch-loading {
  margin: 16px 0;
}
.launch-divider {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0 6px;
  font-size: 0.8rem;
  color: color-mix(in oklab, var(--ion-text-color) 62%, transparent);
}
.launch-divider::before,
.launch-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--ion-border-color);
}
.shell-footnote {
  margin: 16px 0 0;
  font-size: 0.8rem;
  line-height: 1.5;
  color: color-mix(in oklab, var(--ion-text-color) 68%, transparent);
}
</style>
