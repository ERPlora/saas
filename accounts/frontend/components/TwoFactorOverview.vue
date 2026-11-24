<script setup lang="ts">
// The index of the two-factor settings (allauth's `mfa/index.html`): the authenticator app, its recovery codes and
// «Trusted browsers» (ACCOUNTS-F17), as the page reads them. Each button asks the page, which holds the state and the
// calls; only «Continue» leaves on its own.
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import type { Authenticator } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

defineProps<{
  /** Where to go on once the app is on (`?next=`, a path of this site only). */
  next: string | undefined;
  totpOn: boolean;
  recoveryAuthenticator: Extract<Authenticator, { type: 'recovery_codes' }> | undefined;
  /** Until when this browser is trusted: a date, `null` (not trusted), `undefined` (not known yet, or not readable). */
  trustedUntil: string | null | undefined;
  trustUnknown: boolean;
  /** «Stop trusting all browsers» went through. */
  trustRevoked: boolean;
  busy: boolean;
}>();
defineEmits<{ turnOff: []; setUp: []; viewCodes: []; regenerate: []; revokeTrust: [] }>();

const ICONS = {
  app: ionIconSrc('lucide:smartphone'),
  codes: ionIconSrc('lucide:key-round'),
  trust: ionIconSrc('laptop-outline'),
};

const { locale } = useI18n();

/** On to `next`, a page of Django (the admin) or of the SPA: a full load brings what the session now has. */
function goOn(path: string): void {
  location.assign(path);
}
</script>

<template>
  <InlineFeedback
    v-if="next && !totpOn"
    tone="warning"
    class="notice"
    data-testid="mfa-required"
  >
    {{ $t('accounts.twoFactor.requiredToContinue') }}
  </InlineFeedback>
  <ion-button
    v-if="next && totpOn"
    data-testid="mfa-continue"
    color="primary"
    expand="block"
    @click="goOn(next)"
  >
    {{ $t('accounts.twoFactor.continue') }}
  </ion-button>
  <div
    class="auth-section"
    data-testid="totp-section"
  >
    <div class="auth-section-head">
      <ion-icon
        class="auth-section-icon"
        :icon="ICONS.app"
        aria-hidden="true"
      />
      <h2>{{ $t('accounts.twoFactor.authenticatorApp') }}</h2>
      <span
        class="pill"
        :class="{ off: !totpOn }"
        data-testid="totp-pill"
      >{{ totpOn ? $t('accounts.twoFactor.on') : $t('accounts.twoFactor.off') }}</span>
    </div>
    <template v-if="totpOn">
      <p class="auth-lead">
        {{ $t('accounts.twoFactor.totpOnLead') }}
      </p>
      <ion-button
        data-testid="totp-turn-off"
        fill="outline"
        expand="block"
        :disabled="busy"
        @click="$emit('turnOff')"
      >
        {{ $t('accounts.twoFactor.turnOff') }}
      </ion-button>
    </template>
    <template v-else>
      <p class="auth-lead">
        {{ $t('accounts.twoFactor.totpOffLead') }}
      </p>
      <ion-button
        data-testid="totp-set-up"
        color="primary"
        expand="block"
        :disabled="busy"
        @click="$emit('setUp')"
      >
        {{ $t('accounts.twoFactor.setUp') }}
      </ion-button>
    </template>
  </div>

  <div
    v-if="totpOn"
    class="auth-section"
    data-testid="recovery-section"
  >
    <div class="auth-section-head">
      <ion-icon
        class="auth-section-icon"
        :icon="ICONS.codes"
        aria-hidden="true"
      />
      <h2>{{ $t('accounts.twoFactor.recoveryCodes') }}</h2>
    </div>
    <template v-if="recoveryAuthenticator?.unused_code_count">
      <p class="auth-lead">
        {{
          $t(
            'accounts.twoFactor.recoveryUnused',
            { unused: recoveryAuthenticator.unused_code_count },
            recoveryAuthenticator.unused_code_count,
          )
        }}
      </p>
      <ion-button
        data-testid="recovery-view"
        fill="outline"
        expand="block"
        :disabled="busy"
        @click="$emit('viewCodes')"
      >
        {{ $t('accounts.twoFactor.view') }}
      </ion-button>
      <ion-button
        data-testid="recovery-generate-new"
        fill="clear"
        expand="block"
        class="after"
        :disabled="busy"
        @click="$emit('regenerate')"
      >
        {{ $t('accounts.twoFactor.generateNew') }}
      </ion-button>
    </template>
    <template v-else-if="recoveryAuthenticator">
      <!-- All used: the warning, not a «0 unused» that reads as if all were well. -->
      <div
        class="non-field-error"
        data-testid="recovery-all-used"
      >
        {{ $t('accounts.twoFactor.recoveryAllUsed') }}
      </div>
      <ion-button
        data-testid="recovery-generate"
        color="primary"
        expand="block"
        :disabled="busy"
        @click="$emit('regenerate')"
      >
        {{ $t('accounts.twoFactor.generateNewCodes') }}
      </ion-button>
    </template>
    <template v-else>
      <p class="auth-lead">
        {{ $t('accounts.twoFactor.recoveryNoneLead') }}
      </p>
      <ion-button
        data-testid="recovery-generate"
        color="primary"
        expand="block"
        :disabled="busy"
        @click="$emit('regenerate')"
      >
        {{ $t('accounts.twoFactor.generateRecoveryCodes') }}
      </ion-button>
    </template>
  </div>

  <div
    v-if="totpOn"
    class="auth-section"
    data-testid="trust-section"
  >
    <div class="auth-section-head">
      <ion-icon
        class="auth-section-icon"
        :icon="ICONS.trust"
        aria-hidden="true"
      />
      <h2>{{ $t('accounts.twoFactor.trusted.title') }}</h2>
    </div>
    <p
      class="auth-lead"
      data-testid="trust-lead"
    >
      {{ $t('accounts.twoFactor.trusted.lead') }}
    </p>
    <p
      v-if="trustedUntil !== undefined || trustUnknown"
      class="auth-lead"
      data-testid="trust-this"
    >
      {{
        trustUnknown
          ? $t('accounts.twoFactor.trusted.unknown')
          : trustedUntil
            ? $t('accounts.twoFactor.trusted.thisUntil', { date: formatDateTime(trustedUntil, locale) })
            : $t('accounts.twoFactor.trusted.thisNot')
      }}
    </p>
    <p
      v-if="trustRevoked"
      class="auth-lead"
      role="status"
      data-testid="trust-done"
    >
      {{ $t('accounts.twoFactor.trusted.revoked') }}
    </p>
    <ion-button
      data-testid="trust-revoke"
      fill="outline"
      expand="block"
      :disabled="busy"
      @click="$emit('revokeTrust')"
    >
      {{ $t('accounts.twoFactor.trusted.revoke') }}
    </ion-button>
  </div>
</template>

<style scoped src="./auth-card.css"></style>
<style scoped>
.notice {
  margin-bottom: 0.85rem;
}
</style>
