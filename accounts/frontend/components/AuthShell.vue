<script setup lang="ts">
// The frame of every account screen (sign-in, its errors, the launcher), ported from ERPlora/saas's
// partials `account/_auth_header.html` + `_auth_shell_top.html` + `_auth_shell_bottom.html`: the
// back arrow home (Lucide's, as the template had it), the logo with «ERPlora Cloud» and a subtitle,
// a glass card holding the screen (default slot) and an optional foot under the card (`foot`).
// `.auth-title` and `.auth-lead` in the card are styled here, as `_auth_styles.html` did.
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonCard, IonCardContent, IonContent, IonHeader, IonIcon, IonPage, IonToolbar } from '@ionic/vue';

defineProps<{
  /** The monospaced line under «ERPlora Cloud» (already translated). */
  subtitle: string;
}>();

/** Home of the SaaS: the root, which Django sends to the launcher. */
const HOME = '/';
const BACK_ICON = ionIconSrc('lucide:arrow-left');
</script>

<template>
  <ion-page>
    <ion-header class="ion-no-border auth-header">
      <ion-toolbar class="auth-toolbar">
        <ion-buttons slot="start">
          <ion-button
            :href="HOME"
            fill="clear"
            shape="round"
            class="auth-back"
            :aria-label="$t('accounts.login.backToHome')"
          >
            <ion-icon
              slot="icon-only"
              class="auth-back-icon"
              :icon="BACK_ICON"
              aria-hidden="true"
            />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>

    <ion-content class="auth-content">
      <div class="login-shell">
        <div class="auth-card">
          <div class="brand">
            <span
              class="erp-logo lg"
              role="img"
              :aria-label="$t('accounts.login.brand')"
            >
              <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
              <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
              <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
            </span>
            <div>
              <h1 class="biz-name">
                ERPlora Cloud
              </h1>
              <div class="biz-sub">
                {{ subtitle }}
              </div>
            </div>
          </div>

          <ion-card class="glass">
            <ion-card-content class="ion-padding">
              <slot />
            </ion-card-content>
          </ion-card>

          <slot name="foot" />
        </div>
      </div>
    </ion-content>
  </ion-page>
</template>

<style scoped>
/* Ported from `templates/account/_auth_styles.html`. A screen that asks for credentials is outside
   the shell's chrome (App.vue): full bleed, not the rounded card the shell gives every page's
   content (polish.css, «Content area = card-like surface»), as its immersive mode does. */
ion-router-outlet#main.split-pane-main > .ion-page > ion-content.auth-content,
.auth-content {
  --background:
    radial-gradient(50% 40% at 70% 20%, color-mix(in oklch, var(--ion-color-primary) 10%, transparent) 0%, transparent 60%),
    radial-gradient(40% 35% at 15% 80%, color-mix(in oklch, var(--mod-purple, oklch(58% 0.17 295)) 6%, transparent) 0%, transparent 70%),
    var(--ion-color-step-50);
  --padding-start: 0px;
  --padding-end: 0px;
  --padding-top: 0px;
  --padding-bottom: 0px;
  border-radius: 0;
}
ion-router-outlet#main.split-pane-main > .ion-page > ion-content.auth-content::part(background),
ion-router-outlet#main.split-pane-main > .ion-page > ion-content.auth-content::part(scroll) {
  border-radius: 0;
}
/* The Android app lays the page out edge to edge and hands it the system's bar at the bottom as the bottom safe
   area (saas#166): the scroll area ends where that bar begins, so no line of the screen ever lies under it, as in
   Chrome and as the Hub's content ends above its tab bar. The background still runs to the edge. */
.auth-content::part(scroll) {
  bottom: var(--ion-safe-area-bottom, 0px);
}
.login-shell {
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 2rem 1rem;
}
.auth-card {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.75rem;
}
.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}
.biz-name {
  margin: 0;
  font-weight: 600;
  font-size: 1.65rem;
  letter-spacing: -0.02em;
  text-align: center;
}
.biz-sub {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: color-mix(in oklch, var(--ion-text-color) 50%, transparent);
  margin-top: 0.4rem;
  text-align: center;
}
.auth-card ion-card {
  width: 100%;
  margin: 0;
  overflow: visible;
}
.auth-card ion-card.glass {
  --background: transparent;
  background: color-mix(in oklch, var(--ion-background-color) 88%, transparent);
  backdrop-filter: blur(8px);
  border: 1px solid color-mix(in oklch, var(--ion-text-color) 12%, transparent);
  box-shadow: 0 12px 40px -14px rgba(0, 0, 0, 0.18);
  border-radius: 14px;
  color: var(--ion-text-color);
}
.auth-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
}
.auth-toolbar {
  --background: transparent;
  --border-width: 0;
}
.auth-back {
  --color: color-mix(in oklch, var(--ion-text-color) 60%, transparent);
  text-transform: none;
  font-size: 13px;
}
.auth-back:hover {
  --color: var(--ion-text-color);
}
/* The template's `<iconify-icon width="22" height="22">`; scoped by the button to beat ion-buttons'
   `ion-icon[slot="icon-only"] { font-size: 1.65em }`. */
.auth-back .auth-back-icon {
  font-size: 22px;
}
:slotted(.auth-title) {
  font-size: 1.05rem;
  font-weight: 600;
  text-align: center;
  margin: 0.35rem 0 0.5rem;
}
:slotted(.auth-lead) {
  font-size: 13.5px;
  line-height: 1.55;
  color: color-mix(in oklch, var(--ion-text-color) 70%, transparent);
  margin: 0 0 1rem;
  text-align: center;
}
</style>
