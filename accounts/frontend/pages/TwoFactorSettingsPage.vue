<script setup lang="ts">
// The two-factor settings (`/2fa`), over allauth.headless: one page whose views are the templates
// `mfa/index.html` (the authenticator app and, with it on, the recovery codes),
// `mfa/totp/activate_form.html`, `mfa/totp/deactivate_form.html`, `mfa/recovery_codes/index.html`
// and `mfa/recovery_codes/generate.html`, same structure and texts; the URL stays `/2fa`.
//
// - A change that needs a recent login (allauth's `reauthentication_required`) goes to
//   `/reauthenticate` with allauth's flows and comes back here; a session that ended, to the sign-in.
//   Except «Turn on»: allauth issues a new secret on every GET of the setup, so going away and back
//   would show another QR and the scanned one would fail. It confirms right here (password or code,
//   as allauth lists) and posts the same code again; the secret stays in allauth's session.
// - 2FA switched off on the server (`ACCOUNTS_MFA_ENABLED`: its endpoints answer 404) sends to the
//   launcher with `?notice=mfa_unavailable`, without asking when `spa-config.mfaEnabled` already says so.
// - The QR is drawn here from allauth's `otpauth://` URL, as a data-URI image (CSP: `img-src data:`).
// - Turning the app on makes allauth generate the recovery codes: they are shown right away, once.
// - `?next=` (a path of this site): the staff the admin keeps out without the app (ACCOUNTS-F20) land here; the page
//   says the app is needed to go on and, once it is on, «Continue» goes back there with a full load (a page of Django).
//   «Back to settings» goes to Account › Security, where the «Two-step verification» row is.
// - «Trusted browsers» (ACCOUNTS-F17), with the app on, read apart from the authenticators (`browser-trust.ts`).
import {
  ApiError,
  type Authenticator,
  createAllauthClient,
  type FieldErrors,
  isReauthenticationRequired,
  type RecoveryCodes,
  type TotpSetup,
  useLiveClient,
} from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonSpinner } from '@ionic/vue';
import QRCode from 'qrcode';
import { computed, onMounted, shallowRef, watchEffect } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import { useBrowserTrust } from '../browser-trust';
import AuthShell from '../components/AuthShell.vue';
import RecoveryCodesView from '../components/RecoveryCodesView.vue';
import TotpActivateView from '../components/TotpActivateView.vue';
import TwoFactorOverview from '../components/TwoFactorOverview.vue';
import { localNext } from '../next';
import { ACCOUNT, LAUNCHER } from '../paths';

type View = 'index' | 'activate' | 'deactivate' | 'recoveryCodes' | 'regenerate';
/** How «Turn on» confirms a recent login: allauth's `reauthenticate` or `mfa_reauthenticate`. */
type ConfirmWith = 'password' | 'code';

const HERE = '/2fa';
const REAUTHENTICATE = '/reauthenticate';
/** «Back to settings»: Account › Security, the page of the «Two-step verification» row. */
const SECURITY = `${ACCOUNT}/security`;
/** A server with 2FA switched off sends to the launcher with a notice; «Back to settings» goes there too. */
const UNAVAILABLE = { path: LAUNCHER, query: { notice: 'mfa_unavailable' } };
/** allauth's flows that confirm a recent login: the password, the authenticator (or a recovery code). */
const PASSWORD_FLOW = 'reauthenticate';
const CODE_FLOW = 'mfa_reauthenticate';
const NON_FIELD = '__all__';
const QR_OPTIONS = { margin: 1, width: 220 };
const ICONS = {
  off: ionIconSrc('lucide:shield-x'),
  regenerate: ionIconSrc('lucide:refresh-cw'),
};
const TITLES: Record<View, string> = {
  index: 'accounts.twoFactor.title',
  activate: 'accounts.twoFactor.activate.title',
  deactivate: 'accounts.twoFactor.deactivate.title',
  recoveryCodes: 'accounts.twoFactor.codes.title',
  regenerate: 'accounts.twoFactor.regenerate.title',
};

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
/** Where to go on once the app is on (`?next=`, a path of this site only). */
const next = localNext(route.query.next);
/** This page as «Confirm it's you» and the sign-in come back to it: with its `next`. */
const comeBack = next ? `${HERE}?${new URLSearchParams({ next })}` : HERE;
const client = useLiveClient();
const config = client.config;
const auth = createAllauthClient(config);

const status = shallowRef<'loading' | 'ready' | 'error' | 'leaving'>('loading');
const view = shallowRef<View>('index');
const authenticators = shallowRef<Authenticator[]>([]);
const setup = shallowRef<TotpSetup | null>(null);
const qrDataUrl = shallowRef('');
const recovery = shallowRef<RecoveryCodes | null>(null);
/** The view «Generate new codes» was opened from, where «Cancel» goes back. */
const regenerateFrom = shallowRef<View>('index');
const code = shallowRef('');
/** «Turn on» waiting for a recent login, and with what; `null` shows the setup. */
const confirmWith = shallowRef<ConfirmWith | null>(null);
const confirmPassword = shallowRef('');
const confirmCode = shallowRef('');
const busy = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');
const { trustedUntil, trustUnknown, trustRevoked, loadTrust, revokeTrust: revoke } = useBrowserTrust(client);

const totpOn = computed(() => authenticators.value.some((a) => a.type === 'totp'));
const recoveryAuthenticator = computed(() => {
  const found = authenticators.value.find((a) => a.type === 'recovery_codes');
  return found?.type === 'recovery_codes' ? found : undefined;
});
const unusedToReplace = computed(() =>
  regenerateFrom.value === 'recoveryCodes' && recovery.value
    ? recovery.value.unusedCodeCount
    : (recoveryAuthenticator.value?.unused_code_count ?? 0),
);

watchEffect(() => {
  document.title = `${t(TITLES[view.value])} - ERPlora Cloud`;
});

/**
 * A failed call: a recent login missing (→ confirm it, then back here), the session gone (→ the
 * sign-in), allauth's messages (the code's under its input in the setup, the rest above), or the
 * network.
 */
function fail(error: unknown): void {
  if (isReauthenticationRequired(error)) {
    const method = error.flows.includes(CODE_FLOW) ? 'totp' : 'password';
    void router.push({ path: REAUTHENTICATE, query: { next: comeBack, method, flows: error.flows.join(',') } });
  } else if (error instanceof ApiError && error.code === 'not_authenticated') {
    void router.replace({ path: LAUNCHER, query: { next: comeBack } });
  } else if (error instanceof ApiError && error.fields) {
    const input = shownInput();
    const { [NON_FIELD]: whole, ...rest } = error.fields;
    const under = input ? rest[input] : undefined;
    if (input) delete rest[input];
    fields.value = input && under !== undefined ? { [input]: under } : {};
    failure.value = [whole, ...Object.values(rest)].filter(Boolean).join(' ');
  } else {
    failure.value = t('accounts.twoFactor.failed');
  }
}

/** The input on screen, whose allauth error paints under it (`param`), if any. */
function shownInput(): string | undefined {
  if (view.value !== 'activate') return undefined;
  return confirmWith.value === 'password' ? 'password' : 'code';
}

const revokeTrust = () => run(revoke);

/** The settings, read anew. */
async function load(): Promise<void> {
  if (config.mfaEnabled === false) {
    status.value = 'leaving';
    void router.replace(UNAVAILABLE);
    return;
  }
  status.value = 'loading';
  fields.value = {};
  failure.value = '';
  try {
    authenticators.value = await auth.authenticators();
    view.value = 'index';
    status.value = 'ready';
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      status.value = 'leaving';
      void router.replace(UNAVAILABLE);
    } else if (isReauthenticationRequired(error) || (error instanceof ApiError && error.code === 'not_authenticated')) {
      status.value = 'leaving';
      fail(error);
    } else {
      status.value = 'error';
    }
  }
}

/** One action of a view: one at a time, its errors shown by `fail`. */
async function run(task: () => Promise<void>): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  fields.value = {};
  failure.value = '';
  try {
    await task();
  } catch (error) {
    fail(error);
  } finally {
    busy.value = false;
  }
}

function show(next: View): void {
  fields.value = {};
  failure.value = '';
  confirmWith.value = null;
  view.value = next;
}

const refresh = async () => {
  authenticators.value = await auth.authenticators();
  show('index');
};

const openSetup = () =>
  run(async () => {
    const totp = await auth.totpActivateGet();
    if (totp.active) return refresh(); // Turned on meanwhile (another tab).
    setup.value = totp.setup;
    qrDataUrl.value = await QRCode.toDataURL(totp.setup.totpUrl, QR_OPTIONS);
    code.value = '';
    show('activate');
  });

/** Posts the code of the setup; a missing recent login is confirmed here, not on another page. */
async function activate(): Promise<void> {
  try {
    await auth.totpActivatePost(code.value);
  } catch (error) {
    if (!isReauthenticationRequired(error)) throw error;
    if (error.flows.includes(PASSWORD_FLOW)) confirmWith.value = 'password';
    else if (error.flows.includes(CODE_FLOW)) confirmWith.value = 'code';
    else throw error;
    confirmPassword.value = '';
    confirmCode.value = '';
    return;
  }
  await afterActivation();
}

async function afterActivation(): Promise<void> {
  authenticators.value = await auth.authenticators();
  // allauth generated the recovery codes with the first authenticator: show them now, once.
  const generated = await auth.recoveryCodesGet();
  if (generated?.unusedCodes.length) {
    recovery.value = generated;
    show('recoveryCodes');
  } else {
    show('index');
  }
}

const turnOn = () => run(activate);

/** The recent login «Turn on» needed, then the same code again (allauth kept the secret). */
const confirmAndTurnOn = () =>
  run(async () => {
    if (confirmWith.value === 'password') await auth.reauthenticate(confirmPassword.value);
    else await auth.mfaReauthenticate(confirmCode.value);
    confirmWith.value = null;
    await activate();
  });

function cancelConfirm(): void {
  fields.value = {};
  failure.value = '';
  confirmWith.value = null;
}

const turnOff = () =>
  run(async () => {
    await auth.totpDeactivate();
    await refresh();
  });

const openCodes = () =>
  run(async () => {
    recovery.value = await auth.recoveryCodesGet();
    show('recoveryCodes');
  });

function openRegenerate(): void {
  regenerateFrom.value = view.value;
  show('regenerate');
}

const regenerate = () =>
  run(async () => {
    recovery.value = await auth.recoveryCodesRegenerate();
    show('recoveryCodes');
  });

const backToIndex = () => run(refresh);

onMounted(() => {
  void load();
  if (config.mfaEnabled !== false) void loadTrust();
});
</script>

<template>
  <AuthShell :subtitle="$t('accounts.twoFactor.title')">
    <div
      v-if="status === 'loading'"
      class="status"
      data-testid="mfa-loading"
    >
      <ion-spinner name="crescent" />
      <p class="auth-lead">
        {{ $t('accounts.twoFactor.loading') }}
      </p>
    </div>

    <template v-else-if="status === 'error'">
      <div
        class="non-field-error"
        role="alert"
        data-testid="mfa-load-error"
      >
        {{ $t('accounts.twoFactor.loadError') }}
      </div>
      <ion-button
        data-testid="mfa-retry"
        fill="outline"
        expand="block"
        @click="load()"
      >
        {{ $t('accounts.launch.retry') }}
      </ion-button>
    </template>

    <template v-else-if="status === 'ready'">
      <div
        v-if="failure"
        class="non-field-error"
        role="alert"
        data-testid="failure"
      >
        {{ failure }}
      </div>

      <TwoFactorOverview
        v-if="view === 'index'"
        :next="next"
        :totp-on="totpOn"
        :recovery-authenticator="recoveryAuthenticator"
        :trusted-until="trustedUntil"
        :trust-unknown="trustUnknown"
        :trust-revoked="trustRevoked"
        :busy="busy"
        @turn-off="show('deactivate')"
        @set-up="openSetup()"
        @view-codes="openCodes()"
        @regenerate="openRegenerate()"
        @revoke-trust="revokeTrust()"
      />

      <TotpActivateView
        v-else-if="view === 'activate' && setup"
        v-model:code="code"
        v-model:confirm-password="confirmPassword"
        v-model:confirm-code="confirmCode"
        :setup="setup"
        :qr-data-url="qrDataUrl"
        :confirm-with="confirmWith"
        :busy="busy"
        :fields="fields"
        @turn-on="turnOn()"
        @confirm="confirmAndTurnOn()"
        @cancel-confirm="cancelConfirm()"
        @cancel="show('index')"
      />

      <div
        v-else-if="view === 'deactivate'"
        data-testid="deactivate-view"
      >
        <div class="auth-mark">
          <ion-icon
            class="auth-mark-icon"
            :icon="ICONS.off"
            aria-hidden="true"
          />
        </div>
        <h2 class="auth-title">
          {{ $t('accounts.twoFactor.deactivate.title') }}
        </h2>
        <p
          class="auth-lead"
          data-testid="deactivate-lead"
        >
          {{ $t('accounts.twoFactor.deactivate.lead') }}
        </p>
        <ion-button
          data-testid="deactivate-submit"
          color="danger"
          size="large"
          expand="block"
          :disabled="busy"
          @click="turnOff()"
        >
          {{ $t('accounts.twoFactor.deactivate.turnOff') }}
        </ion-button>
        <ion-button
          data-testid="deactivate-keep"
          fill="clear"
          expand="block"
          class="after"
          :disabled="busy"
          @click="show('index')"
        >
          {{ $t('accounts.twoFactor.deactivate.keepOn') }}
        </ion-button>
      </div>

      <RecoveryCodesView
        v-else-if="view === 'recoveryCodes'"
        :recovery="recovery"
        :busy="busy"
        @regenerate="openRegenerate()"
        @back="backToIndex()"
      />

      <div
        v-else-if="view === 'regenerate'"
        data-testid="regenerate-view"
      >
        <div class="auth-mark">
          <ion-icon
            class="auth-mark-icon"
            :icon="ICONS.regenerate"
            aria-hidden="true"
          />
        </div>
        <h2 class="auth-title">
          {{ $t('accounts.twoFactor.regenerate.title') }}
        </h2>
        <p
          class="auth-lead"
          data-testid="regenerate-lead"
        >
          {{
            unusedToReplace
              ? $t('accounts.twoFactor.regenerate.replaces', { count: unusedToReplace }, unusedToReplace)
              : $t('accounts.twoFactor.regenerate.nothingLeft')
          }}
        </p>
        <ion-button
          data-testid="regenerate-submit"
          color="primary"
          size="large"
          expand="block"
          :disabled="busy"
          @click="regenerate()"
        >
          {{ $t('accounts.twoFactor.regenerate.generate') }}
        </ion-button>
        <ion-button
          data-testid="regenerate-cancel"
          fill="clear"
          expand="block"
          class="after"
          :disabled="busy"
          @click="regenerateFrom === 'recoveryCodes' ? show('recoveryCodes') : show('index')"
        >
          {{ $t('accounts.twoFactor.regenerate.cancel') }}
        </ion-button>
      </div>
    </template>

    <template #foot>
      <p class="foot">
        <router-link :to="SECURITY">
          {{ $t('accounts.twoFactor.backToSettings') }}
        </router-link>
      </p>
    </template>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
