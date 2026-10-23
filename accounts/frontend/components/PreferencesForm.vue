<script setup lang="ts">
// Account → Preferences (mockups `account.html` «preferences»; no currency nor palette: one palette, charged in
// euros, ronda 17): the live `accounts.preferences.get` and three cards whose controls save on their own
// (`accounts.preferences.update`, only what changed), each ending in «Preferences saved»:
//   - Appearance: system, light or dark, the shell's theme (`setThemeMode`), painted at once and kept in the
//     account; the account's mode is painted when the preferences arrive (also when another tab changes it);
//   - Language: the account's (`User.language`, which the mails and the jump to a business read): the panel
//     switches to it at once (`<html lang>` too);
//   - Mails: «Security, invoices and payments» is always on; «Business notices» (the mail that a business is ready)
//     is a switch. No «ERPlora news»: ERPlora sends no such mail (ACCOUNTS-F23).
// A refusal puts the control back and says why. A failed load is said with «Retry», also when no answer comes in
// time: never a skeleton for ever (audit 2026-10-14 R-08).
import { setThemeMode, themeMode, toastError, toastSuccess } from '@erplora/ui/shell';
import { useCommand, useLive } from '@erplora/ui/sdk';
import {
  IonCard,
  IonCardContent,
  IonItem,
  IonLabel,
  IonList,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
  IonSkeletonText,
  IonToggle,
} from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import LoadFailed from '../../../frontend/LoadFailed.vue';
import { useLiveState } from '../../../frontend/live-state';
import type { AccountLanguage, AccountThemeMode, PreferencesOut, PreferencesUpdateIn } from '../../../frontend/sdk-types';
import { useErrorText } from '../error-text';

const THEMES: AccountThemeMode[] = ['system', 'light', 'dark'];
/** Each language in its own name (`settings.LANGUAGES`). */
const LANGUAGES: Array<{ code: AccountLanguage; name: string }> = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Español' },
];

const { t, locale } = useI18n();
const { text } = useErrorText();
const live = useLive('accounts.preferences.get');
const state = useLiveState(live);
const update = useCommand('accounts.preferences.update');

const language = shallowRef<AccountLanguage>('en');
const hubAlerts = shallowRef(false);
const loaded = computed(() => live.data.value);

function take(now: PreferencesOut): void {
  if (themeMode.value !== now.theme_mode) setThemeMode(now.theme_mode);
  language.value = now.language;
  hubAlerts.value = now.hub_alerts;
}

watch(live.data, (now) => now && take(now), { immediate: true });

/** Saves `change`; on a refusal, `undo` puts the control back. */
async function save(change: PreferencesUpdateIn, undo: () => void): Promise<boolean> {
  try {
    await update.run(change);
    return true;
  } catch {
    undo();
    void toastError(text(update.error.value));
    return false;
  }
}

async function chooseTheme(event: CustomEvent<{ value?: unknown }>): Promise<void> {
  const mode = String(event.detail.value) as AccountThemeMode;
  const before = themeMode.value;
  if (!THEMES.includes(mode) || mode === before) return;
  setThemeMode(mode);
  if (await save({ theme_mode: mode }, () => setThemeMode(before))) void toastSuccess(t('accounts.account.preferences.saved'));
}

async function chooseLanguage(event: CustomEvent<{ value?: unknown }>): Promise<void> {
  const chosen = String(event.detail.value) as AccountLanguage;
  const before = language.value;
  if (chosen === before || !LANGUAGES.some((option) => option.code === chosen)) return;
  language.value = chosen;
  if (!(await save({ language: chosen }, () => (language.value = before)))) return;
  locale.value = chosen;
  document.documentElement.lang = chosen;
  void toastSuccess(t('accounts.account.preferences.saved'));
}

async function toggleBusinessNotices(event: CustomEvent<{ checked?: boolean }>): Promise<void> {
  const before = hubAlerts.value;
  const checked = event.detail.checked === true;
  if (checked === before) return;
  hubAlerts.value = checked;
  if (await save({ hub_alerts: checked }, () => (hubAlerts.value = before))) void toastSuccess(t('accounts.account.preferences.saved'));
}
</script>

<template>
  <div class="tab-stack">
    <LoadFailed
      v-if="state.failed.value"
      testid="preferences-error"
      retry-testid="preferences-retry"
      :heading="$t('accounts.account.preferences.loadError')"
      @retry="state.retry()"
    />

    <ion-card
      v-else-if="!loaded"
      data-testid="preferences-loading"
      :aria-label="$t('accounts.account.loading')"
    >
      <ion-card-content class="ion-padding">
        <ion-skeleton-text
          animated
          style="width: 30%; height: 16px"
        />
        <ion-skeleton-text
          animated
          style="width: 100%; max-width: 420px; height: 36px; margin-top: 16px"
        />
      </ion-card-content>
    </ion-card>

    <template v-else>
      <ion-card data-testid="preferences-appearance">
        <ion-card-content class="ion-padding">
          <h2 class="card-title">
            {{ $t('accounts.account.preferences.appearance') }}
          </h2>
          <p class="card-text">
            {{ $t('accounts.account.preferences.appearanceLead') }}
          </p>
        </ion-card-content>
        <!-- Outside `ion-card-content`: a segment there takes the card's type and grows (README §6.14). -->
        <div class="segment-pad">
          <ion-segment
            data-testid="preferences-theme"
            class="theme-segment"
            :value="themeMode"
            :aria-label="$t('accounts.account.preferences.appearance')"
            @ion-change="chooseTheme"
          >
            <ion-segment-button
              v-for="mode in THEMES"
              :key="mode"
              :value="mode"
            >
              <ion-label>{{ $t(`accounts.account.preferences.themes.${mode}`) }}</ion-label>
            </ion-segment-button>
          </ion-segment>
        </div>
      </ion-card>

      <ion-card data-testid="preferences-language-card">
        <ion-card-content class="ion-padding">
          <h2 class="card-title">
            {{ $t('accounts.account.preferences.languageHeading') }}
          </h2>
          <div class="field-grid cols-2">
            <ion-select
              data-testid="preferences-language"
              mode="md"
              fill="outline"
              interface="popover"
              label-placement="floating"
              :label="$t('accounts.account.preferences.language')"
              :helper-text="$t('accounts.account.preferences.languageHint')"
              :value="language"
              @ion-change="chooseLanguage"
            >
              <ion-select-option
                v-for="option in LANGUAGES"
                :key="option.code"
                :value="option.code"
                :lang="option.code"
              >
                {{ option.name }}
              </ion-select-option>
            </ion-select>
          </div>
        </ion-card-content>
      </ion-card>

      <ion-card data-testid="preferences-mails">
        <ion-card-content class="ion-padding">
          <h2 class="card-title">
            {{ $t('accounts.account.preferences.mails') }}
          </h2>
          <ion-list
            lines="full"
            class="mail-list"
          >
            <ion-item>
              <ion-toggle
                data-testid="preferences-invoices"
                :checked="true"
                :disabled="true"
              >
                <span class="toggle-title">{{ $t('accounts.account.preferences.invoices') }}</span>
                <span class="toggle-hint">{{ $t('accounts.account.preferences.invoicesHint') }}</span>
              </ion-toggle>
            </ion-item>
            <ion-item>
              <ion-toggle
                data-testid="preferences-hub-alerts"
                :checked="hubAlerts"
                @ion-change="toggleBusinessNotices"
              >
                <span class="toggle-title">{{ $t('accounts.account.preferences.hubAlerts') }}</span>
                <span class="toggle-hint">{{ $t('accounts.account.preferences.hubAlertsHint') }}</span>
              </ion-toggle>
            </ion-item>
          </ion-list>
        </ion-card-content>
      </ion-card>
    </template>
  </div>
</template>

<style scoped src="./account-card.css"></style>
<style scoped>
.tab-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.segment-pad {
  padding: 0 16px 16px;
}
/* The mockups' appearance switch: a grey track with the chosen mode on a raised pill (the shell's segments are
   transparent, made for the tabbar). */
.theme-segment {
  max-width: 420px;
  --background: color-mix(in oklab, var(--ion-text-color) 7%, transparent);
  border-radius: 12px;
}
.theme-segment ion-segment-button {
  min-height: 36px;
}
/* A 44px target on touch (audit 2026-10-14, R-13), with the touch query of `@erplora/ui`'s DataTable. */
@media (pointer: coarse), (max-width: 834px) {
  .theme-segment ion-segment-button {
    min-height: 44px;
  }
}
.theme-segment ion-segment-button::part(indicator-background) {
  background: var(--ion-card-background, #fff);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}
.mail-list {
  margin-top: 8px;
  padding: 0;
  background: transparent;
}
.mail-list ion-item {
  --padding-start: 0;
  --inner-padding-end: 0;
  --background: transparent;
}
.mail-list ion-toggle {
  white-space: normal;
}
/* Ionic's toggle label is one line with «…»: a title or a hint wraps instead of being cut (the always-on row's hint
   names every mail that goes, ACCOUNTS-F23). */
.toggle-title,
.toggle-hint {
  white-space: normal;
}
.toggle-title {
  display: block;
  color: var(--ion-text-color);
}
/* «Security, invoices and payments» cannot be turned off, yet the mails it names must read as any text: Ionic dims a
   disabled toggle whole (0.3 in ios, 0.38 in md), its words included; only its switch stays dimmed (ACCOUNTS-F23). */
.mail-list ion-toggle.toggle-disabled {
  opacity: 1;
}
.mail-list ion-toggle.toggle-disabled::part(track),
.mail-list ion-toggle.toggle-disabled::part(handle) {
  opacity: 0.5;
}
.toggle-hint {
  display: block;
  margin-top: 2px;
  font-size: 0.82rem;
  color: var(--ep-text-secondary, color-mix(in oklab, var(--ion-text-color) 68%, transparent));
}
</style>
