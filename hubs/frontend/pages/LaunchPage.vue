<script setup lang="ts">
// The entry of erplora.com and of the apps (`/launch`; Django's `/launch/` and the apps' `/shell/` lead
// here): round 17 §2.2, mockups `launch.html`, README §5. A centred card without the menu
// (`meta.chrome: false`) that never enters a business by itself unless the person just created it or
// is waiting for the only one to be ready:
//   - signed out → «Sign in» and back here (`/login?next=/launch`);
//   - no business → the sign-up form, «or», «Go to the panel»; with a pending invitation the card IS
//     the invitation (accept and enter, decline, or create one's own); after creating, «Preparing»
//     and it opens by itself when the Hub reports it ready (or says it could not be prepared);
//   - one business → «Open X» (disabled while it is prepared, gone while suspended) and «Go to the
//     panel», with why it does not open;
//   - several → the server's order (the last opened first), «Open» on each, «Create another business».
// Live data: `hubs.business.list` (the account's businesses and its pending invitations), its states truthful
// (`useLiveState`, audit 2026-10-14 R-08: no answer in time is an error with «Retry», never a spinner for ever).
// A business that owes an invoice says its real deadline (R-06) and, on the web for whoever may pay it, «Pay the
// invoice» (or «Change card») is the main action, «Open» the second, outlined (R-07, audit 2 S-06; mockups `launch.html`
// «past-due»). A deleted business offers its owner «Recover business» there, within its 90 days (audit 2 R-07).
// Ionic reuses the page when it comes back on screen: its address (`?notice=`) and the tab's title are read then.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { HubIcon, useSession, useSurface } from '@erplora/ui/shell';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonProgressBar, IonSpinner, onIonViewWillEnter } from '@ionic/vue';
import { computed, onMounted, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { useLiveState } from '../../../frontend/live-state';
import LoadFailed from '../../../frontend/LoadFailed.vue';
import type { BusinessRowOut, InvitationOut } from '../../../frontend/sdk-types';
import { preparationFailed, reasonDate, reasonKey, statusPill } from '../business-status';
import BusinessCreateForm from '../components/BusinessCreateForm.vue';
import BusinessPreparing from '../components/BusinessPreparing.vue';
import CardShell from '../components/CardShell.vue';
import DeclineDialog from '../components/DeclineDialog.vue';
import HostName from '../components/HostName.vue';
import RecoverButton from '../components/RecoverButton.vue';
import UnpaidActions from '../components/UnpaidActions.vue';
import { useAcceptInvitation } from '../invitations';
import { useOpenBusiness } from '../open-business';

const HERE = '/launch';
const PANEL = '/businesses';

const { t, locale } = useI18n();
const router = useRouter();
const session = useSession();
const { inApp, isWeb } = useSurface();

const user = computed(() => session.user.value);
const mfaUnavailable = shallowRef(false);
// Signed out there is nothing to follow (and the stream would refuse it): only then no subscription.
// Signing in or out reloads the page (allauth, Django's logout form), so this is decided once.
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
    case 'signedOut':
      return t('hubs.launch.signedOut.title');
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
    case 'signedOut':
      return inApp.value ? t('hubs.launch.signedOut.leadApp') : t('hubs.launch.signedOut.lead');
    case 'preparing':
      return t('hubs.launch.preparing.lead');
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
    case 'signedOut':
      return 'ion:person-outline';
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

// ── What each business says ───────────────────────────────────────────────────────────────────
const pill = (business: BusinessRowOut) => statusPill(business, t, locale.value);

function reason(business: BusinessRowOut, short = false): string {
  const key = reasonKey(business, inApp.value);
  if (!key) return '';
  // With several nothing opens by itself: the neutral «ready in a few seconds».
  if (short && key === 'hubs.reason.preparing') return t('hubs.reason.preparingSoon');
  return t(key, { date: reasonDate(business, locale.value) });
}

/** On the web, whoever may pay a business's unpaid invoice is offered to pay it first (R-07). */
const owes = (business: BusinessRowOut) =>
  isWeb.value && !!business.pay_url && (business.status === 'past_due' || business.status === 'suspended');

function meta(business: BusinessRowOut, withPlan: boolean): string {
  return withPlan && business.plan
    ? `${t('hubs.common.plan', { name: business.plan.name })} · ${business.role_label}`
    : business.role_label;
}

/** Suspended or deleted: «Open» is not offered at all (README §5.3). */
const opensAtAll = (business: BusinessRowOut) => business.status !== 'suspended' && business.status !== 'deleting';

function decline(it: InvitationOut): void {
  declining.value = it;
  declineOpen.value = true;
}

const signIn = () => router.push({ path: '/login', query: { next: HERE } });
const toPanel = () => router.push(PANEL);

/** Each time the page comes on screen (Ionic reuses it): what its address says, and the tab's name. */
function entered(): void {
  mfaUnavailable.value = router.currentRoute.value.query.notice === 'mfa_unavailable';
  document.title = `${t('hubs.launch.pageTitle')} - ERPlora`;
}
onMounted(entered);
onIonViewWillEnter(entered);
</script>

<template>
  <CardShell
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
      <!-- ═══ Signed out ═══ -->
      <div
        v-if="variant === 'signedOut'"
        class="ion-text-center"
      >
        <p class="card-text">
          {{ $t('hubs.launch.signedOut.body') }}
        </p>
        <ion-button
          data-testid="launch-sign-in"
          expand="block"
          size="large"
          class="launch-main"
          @click="signIn"
        >
          <HubIcon
            slot="start"
            name="ion:log-in-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.launch.signedOut.signIn') }}
        </ion-button>
        <ion-button
          data-testid="launch-sign-up"
          class="link-button"
          expand="block"
          fill="clear"
          href="/accounts/signup/?next=/launch"
        >
          <HubIcon
            slot="start"
            name="ion:person-outline"
            aria-hidden="true"
          />
          {{ $t('hubs.launch.signedOut.signUp') }}
        </ion-button>
      </div>

      <template v-else>
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
            :name="created.name"
            :type-name="created.typeName"
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
        <template v-else-if="variant === 'invited' && invitation">
          <ion-button
            data-testid="launch-accept"
            expand="block"
            size="large"
            class="launch-main"
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
              aria-hidden="true"
            />
            {{ $t('hubs.invitation.accept') }}
          </ion-button>
          <ion-button
            data-testid="launch-decline"
            expand="block"
            fill="outline"
            class="btn-neutral"
            :disabled="!!accepting"
            @click="decline(invitation)"
          >
            <HubIcon
              slot="start"
              name="ion:close-outline"
              aria-hidden="true"
            />
            {{ $t('hubs.invitation.decline') }}
          </ion-button>
          <ion-button
            data-testid="launch-create-own"
            class="link-button"
            expand="block"
            fill="clear"
            @click="ownForm = true"
          >
            <HubIcon
              slot="start"
              name="ion:add-outline"
              aria-hidden="true"
            />
            {{ $t('hubs.launch.invited.createOwn') }}
          </ion-button>
        </template>

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

          <template v-if="variant === 'one' && rows[0]">
            <div
              class="launch-biz ion-padding"
              :class="{ 'is-waiting': rows[0].status === 'preparing' }"
              data-testid="launch-business"
            >
              <span class="biz-card__icon"><HubIcon
                name="ion:storefront-outline"
                aria-hidden="true"
              /></span>
              <div class="launch-biz__text">
                <h2>{{ rows[0].name }}</h2>
                <p class="mono launch-biz__url">
                  <HostName :host="rows[0].host" />
                </p>
                <p class="launch-biz__pills">
                  <StatusPill v-bind="pill(rows[0])" />
                  <span class="launch-biz__meta">{{ meta(rows[0], true) }}</span>
                </p>
              </div>
            </div>
            <p
              v-if="reason(rows[0])"
              class="launch-reason"
              :class="{
                'is-warning': rows[0].status === 'past_due',
                'is-danger': rows[0].status === 'suspended' || rows[0].status === 'deleting' || pill(rows[0]).tone === 'danger',
              }"
              data-testid="launch-reason"
            >
              {{ reason(rows[0]) }}
            </p>
            <ion-progress-bar
              v-if="rows[0].status === 'preparing' && pill(rows[0]).tone !== 'danger'"
              type="indeterminate"
              class="launch-progress"
              :aria-label="$t('hubs.preparing.progress')"
            />
            <UnpaidActions
              v-if="owes(rows[0])"
              :business="rows[0]"
              size="large"
              expand="block"
              class="launch-main"
            />
            <RecoverButton
              v-if="rows[0].status === 'deleting'"
              :business="rows[0]"
              size="large"
              expand="block"
              class="launch-main"
            />
            <ion-button
              v-if="opensAtAll(rows[0])"
              data-testid="launch-open"
              expand="block"
              :size="owes(rows[0]) ? undefined : 'large'"
              :fill="owes(rows[0]) ? 'outline' : 'solid'"
              :class="owes(rows[0]) ? 'launch-second' : 'launch-main'"
              :disabled="!rows[0].can_open || !!opening"
              @click="open(rows[0])"
            >
              <ion-spinner
                v-if="opening === rows[0].id"
                slot="start"
                name="crescent"
                aria-hidden="true"
              />
              <HubIcon
                v-else
                slot="start"
                name="ion:log-in-outline"
                aria-hidden="true"
              />
              {{ opening === rows[0].id ? $t('hubs.open.opening', { name: rows[0].name }) : $t('hubs.common.openName', { name: rows[0].name }) }}
            </ion-button>
          </template>

          <div
            v-else
            class="launch-list"
          >
            <div
              v-for="(business, index) in rows"
              :key="business.id"
              class="launch-biz ion-padding"
              :class="{ 'is-waiting': business.status === 'preparing' }"
              data-testid="launch-business"
            >
              <span class="biz-card__icon"><HubIcon
                name="ion:storefront-outline"
                aria-hidden="true"
              /></span>
              <div class="launch-biz__text">
                <h2>{{ business.name }}</h2>
                <p class="mono launch-biz__url">
                  <HostName :host="business.host" />
                </p>
                <p class="launch-biz__pills">
                  <StatusPill v-bind="pill(business)" />
                  <span class="launch-biz__meta">{{ meta(business, false) }}</span>
                  <StatusPill
                    v-if="index === 0 && business.last_opened_at"
                    class="tag-recent"
                    tone="info"
                    :dot="false"
                    :label="$t('hubs.common.lastOpened')"
                  />
                </p>
                <p
                  v-if="reason(business, true)"
                  class="launch-biz__why"
                >
                  {{ reason(business, true) }}
                </p>
                <UnpaidActions
                  v-if="owes(business)"
                  :business="business"
                  named
                  size="small"
                  class="launch-biz__pay"
                />
                <RecoverButton
                  v-if="business.status === 'deleting'"
                  :business="business"
                  named
                  size="small"
                  class="launch-biz__pay"
                />
              </div>
              <ion-button
                v-if="opensAtAll(business)"
                data-testid="launch-open"
                :fill="owes(business) ? 'outline' : 'solid'"
                :aria-label="$t('hubs.common.openName', { name: business.name })"
                :disabled="!business.can_open || !!opening"
                @click="open(business)"
              >
                <ion-spinner
                  v-if="opening === business.id"
                  slot="start"
                  name="crescent"
                  aria-hidden="true"
                />
                <HubIcon
                  v-else
                  slot="start"
                  name="ion:log-in-outline"
                  aria-hidden="true"
                />
                {{ $t('hubs.common.open') }}
              </ion-button>
            </div>
          </div>

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
            @click="router.push({ path: PANEL, query: { create: '1' } })"
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
/* `mock.css` of the mockups (launch-*), with our tokens. */
.card-text {
  margin: 0 0 16px;
  font-size: 0.9rem;
  line-height: 1.5;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.launch-main {
  margin-top: 16px;
}
.launch-second {
  margin-top: 10px;
}
.launch-biz__pay {
  margin-top: 8px;
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
.launch-list {
  display: grid;
  gap: 10px;
}
.launch-biz {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--ion-border-color);
  border-radius: 12px;
  min-width: 0;
}
.biz-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  font-size: 22px;
  color: var(--ion-color-primary);
  background: color-mix(in oklab, var(--ion-color-primary) 12%, transparent);
}
.launch-biz.is-waiting .biz-card__icon {
  color: var(--ion-color-medium);
  background: color-mix(in oklab, var(--ion-color-medium) 12%, transparent);
}
.launch-biz__text {
  flex: 1 1 auto;
  min-width: 0;
}
.launch-biz__text h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.3;
  color: var(--ion-text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.launch-biz__text p {
  margin: 3px 0 0;
  font-size: 0.78rem;
  color: color-mix(in oklab, var(--ion-text-color) 65%, transparent);
}
.mono {
  font-family: var(--font-mono, ui-monospace, monospace);
}
.launch-biz__url {
  overflow-wrap: anywhere;
}
.launch-biz__pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.launch-biz__meta {
  font-size: 0.82rem;
}
.launch-biz__text p.launch-biz__why {
  margin-top: 4px;
  font-size: 0.8rem;
  line-height: 1.35;
  color: color-mix(in oklab, var(--ion-text-color) 70%, transparent);
}
.launch-biz ion-button {
  flex: none;
  min-height: 44px;
}
.launch-reason {
  margin: 12px 2px 0;
  font-size: 0.88rem;
  line-height: 1.45;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.launch-reason.is-warning {
  color: var(--ep-warning-on-tint, color-mix(in oklch, var(--ion-color-warning) 55%, var(--ion-text-color)));
}
.launch-reason.is-danger {
  color: var(--ep-danger-on-tint, var(--ion-color-danger));
}
.launch-progress {
  margin-top: 10px;
  border-radius: 999px;
}
.btn-neutral {
  --color: var(--ion-text-color);
  --border-color: color-mix(in oklab, var(--ion-text-color) 35%, transparent);
}
@media (max-width: 420px) {
  .launch-list .launch-biz > .biz-card__icon {
    display: none;
  }
}
</style>
