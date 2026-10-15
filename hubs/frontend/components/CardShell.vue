<script setup lang="ts">
// The centred-card frame of the launcher (`/launch`) and the invitation (`/invitation`): mockups
// `launch.html` and `invitation.html`, the old SaaS's `_shell_styles.html`. A route with
// `meta.chrome: false`, so no menu: the ERPlora lockup INSIDE the card above the title of every
// state (README §5), the state's icon and title (the page's one heading), its lead, the content
// (default slot) and, under the card, «Signed in as … · Sign out». Signing out is the user menu's
// (`frontend/main.ts`): allauth.headless ends the session, then the launcher's sign-in, as a full load; a
// failure says so and stays.
import { HubIcon, toastError, useSession } from '@erplora/ui/shell';
import { createAllauthClient, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCard, IonCardContent, IonCardHeader, IonCardTitle, IonContent, IonPage } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';

import { LAUNCHER } from '../../../accounts/frontend/paths';

defineProps<{
  /** Icon of the state, over the title (`set:name`, registered). */
  icon: string;
  /** Title of the state: the page's heading. */
  title: string;
  /** The sentence under the title. */
  lead?: string;
}>();

defineSlots<{ default?: () => unknown; lead?: () => unknown }>();

const { t } = useI18n();
const session = useSession();
const auth = createAllauthClient(useLiveClient().config);
const email = computed(() => session.user.value?.email || session.user.value?.label || '');
const signingOut = shallowRef(false);

async function signOut(): Promise<void> {
  signingOut.value = true;
  try {
    const state = await auth.logout();
    if (state.authenticated) throw new Error('still signed in after signing out');
    location.assign(LAUNCHER);
  } catch (error) {
    console.error('saas: sign out failed', error);
    signingOut.value = false;
    void toastError(t('userMenu.logoutFailed'));
  }
}
</script>

<template>
  <ion-page>
    <ion-content class="card-shell-content">
      <div class="shell-page ion-padding">
        <div class="shell-wrap">
          <ion-card class="shell-card">
            <div class="shell-logo">
              <span
                class="erp-lockup md"
                role="img"
                aria-label="ERPlora"
              >
                <span class="erp-logo md">
                  <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
                  <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
                  <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
                </span>
                <span class="erp-wordmark">ERPlora</span>
              </span>
            </div>
            <ion-card-header class="ion-padding ion-text-center">
              <div class="shell-brand">
                <HubIcon
                  class="shell-brand-icon"
                  :name="icon"
                  aria-hidden="true"
                />
                <ion-card-title
                  role="heading"
                  aria-level="1"
                >
                  {{ title }}
                </ion-card-title>
              </div>
            </ion-card-header>
            <ion-card-content class="ion-padding">
              <p
                v-if="lead || $slots.lead"
                class="shell-lead ion-text-center"
              >
                <slot name="lead">
                  {{ lead }}
                </slot>
              </p>
              <slot />
            </ion-card-content>
          </ion-card>

          <div
            v-if="session.user.value"
            class="shell-account"
            data-testid="shell-account"
          >
            <span class="shell-account__who">{{ $t('hubs.common.signedInAs', { email }) }}</span>
            <ion-button
              fill="clear"
              class="shell-account__logout"
              :disabled="signingOut"
              @click="signOut"
            >
              <HubIcon
                slot="start"
                name="ion:log-out-outline"
                aria-hidden="true"
              />
              {{ $t('hubs.common.signOut') }}
            </ion-button>
          </div>
        </div>
      </div>
    </ion-content>
  </ion-page>
</template>

<style scoped src="./buttons.css"></style>
<style scoped>
/* The page around the card: full bleed, not the rounded card the shell gives every page's content
   (polish.css), as the sign-in's AuthShell does. */
ion-router-outlet#main.split-pane-main > .ion-page > ion-content.card-shell-content,
.card-shell-content {
  --background: var(--ion-background-color);
  border-radius: 0;
}
ion-router-outlet#main.split-pane-main > .ion-page > ion-content.card-shell-content::part(background),
ion-router-outlet#main.split-pane-main > .ion-page > ion-content.card-shell-content::part(scroll) {
  border-radius: 0;
}
/* `_shell_styles.html`: the card centred in the viewport, 460 px at most. */
.shell-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}
.shell-wrap {
  width: 100%;
  max-width: 460px;
}
.shell-card {
  margin: 0;
  border-radius: 16px;
  --background: var(--ion-card-background, var(--ion-item-background, #fff));
  border: 1px solid var(--ion-border-color);
  box-shadow: 0 10px 30px -18px rgba(0, 0, 0, 0.25);
}
.shell-logo {
  display: flex;
  justify-content: center;
  margin: 24px 16px 0;
}
.shell-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.shell-brand-icon {
  color: var(--ion-color-primary);
  font-size: 28px;
}
.shell-card ion-card-title {
  font-size: 1.65rem;
  font-weight: 700;
  line-height: 1.2;
  color: var(--ion-text-color);
}
.shell-lead {
  margin: 0 0 16px;
  font-size: 0.95rem;
  line-height: 1.45;
  color: color-mix(in oklab, var(--ion-text-color) 72%, transparent);
}
.shell-account {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 2px 4px;
  margin-top: 12px;
  text-align: center;
}
.shell-account__who {
  font-size: 0.82rem;
  color: color-mix(in oklab, var(--ion-text-color) 62%, transparent);
}
.shell-account__logout {
  min-height: 44px;
  font-size: 0.85rem;
  --color: var(--ion-text-color);
  font-weight: 400;
  text-transform: none;
}
</style>
