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
// - The QR is drawn here from allauth's `otpauth://` URL, as a data-URI image (CSP: `img-src data:`);
//   the codes download as a text file built here, so there is no server route for it.
// - Turning the app on makes allauth generate the recovery codes: they are shown right away, once.
// - «Trusted browsers» (ACCOUNTS-F17), with the app on: whether this browser skips the app's code (ACCOUNTS-F05) and
//   until when (`accounts.browser_trust.get`; allauth keeps no list, so only this one can be told), and «Stop trusting
//   all browsers» (`accounts.browser_trust.revoke`). Read apart from the authenticators: it never holds the page.
import { formatDateTime } from '@erplora/ui/components';
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
import { IonButton, IonIcon, IonInput, IonInputPasswordToggle, IonSpinner } from '@ionic/vue';
import QRCode from 'qrcode';
import { computed, onMounted, shallowRef, watchEffect } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import CodeField from '../components/CodeField.vue';
import { LAUNCHER } from '../paths';

type View = 'index' | 'activate' | 'deactivate' | 'recoveryCodes' | 'regenerate';
/** How «Turn on» confirms a recent login: allauth's `reauthenticate` or `mfa_reauthenticate`. */
type ConfirmWith = 'password' | 'code';

const HERE = '/2fa';
const REAUTHENTICATE = '/reauthenticate';
/** A server with 2FA switched off sends to the launcher with a notice; «Back to settings» goes there too. */
const UNAVAILABLE = { path: LAUNCHER, query: { notice: 'mfa_unavailable' } };
/** allauth's flows that confirm a recent login: the password, the authenticator (or a recovery code). */
const PASSWORD_FLOW = 'reauthenticate';
const CODE_FLOW = 'mfa_reauthenticate';
const NON_FIELD = '__all__';
const DOWNLOAD_NAME = 'erplora-recovery-codes.txt';
/** How long the downloaded file's object URL lives (the browser reads it after the click). */
const DOWNLOAD_URL_TTL_MS = 40_000;
const QR_OPTIONS = { margin: 1, width: 220 };
const ICONS = {
  app: ionIconSrc('lucide:smartphone'),
  password: ionIconSrc('lucide:lock'),
  code: ionIconSrc('lucide:shield-check'),
  codes: ionIconSrc('lucide:key-round'),
  off: ionIconSrc('lucide:shield-x'),
  regenerate: ionIconSrc('lucide:refresh-cw'),
  trust: ionIconSrc('laptop-outline'),
};
const TITLES: Record<View, string> = {
  index: 'accounts.twoFactor.title',
  activate: 'accounts.twoFactor.activate.title',
  deactivate: 'accounts.twoFactor.deactivate.title',
  recoveryCodes: 'accounts.twoFactor.codes.title',
  regenerate: 'accounts.twoFactor.regenerate.title',
};

const { t, locale } = useI18n();
const router = useRouter();
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
/** Until when this browser is trusted: a date, `null` (not trusted), `undefined` (not known yet, or not readable). */
const trustedUntil = shallowRef<string | null | undefined>(undefined);
const trustUnknown = shallowRef(false);
/** «Stop trusting all browsers» went through. */
const trustRevoked = shallowRef(false);

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
    void router.push({ path: REAUTHENTICATE, query: { next: HERE, method, flows: error.flows.join(',') } });
  } else if (error instanceof ApiError && error.code === 'not_authenticated') {
    void router.replace({ path: LAUNCHER, query: { next: HERE } });
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

/** Whether this browser is trusted, and until when; read on its own, it never holds the page. */
async function loadTrust(): Promise<void> {
  trustUnknown.value = false;
  try {
    trustedUntil.value = (await client.api.call('accounts.browser_trust.get')).trusted_until;
  } catch {
    trustedUntil.value = undefined;
    trustUnknown.value = true;
  }
}

const revokeTrust = () =>
  run(async () => {
    trustedUntil.value = (await client.api.call('accounts.browser_trust.revoke')).trusted_until;
    trustUnknown.value = false;
    trustRevoked.value = true;
  });

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

/** The unused codes as a text file, one per line: built here, never a server route. */
function download(): void {
  const codes = recovery.value?.unusedCodes ?? [];
  const url = URL.createObjectURL(new Blob([`${codes.join('\n')}\n`], { type: 'text/plain' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = DOWNLOAD_NAME;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_TTL_MS);
}

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

      <template v-if="view === 'index'">
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
              @click="show('deactivate')"
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
              @click="openSetup()"
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
              @click="openCodes()"
            >
              {{ $t('accounts.twoFactor.view') }}
            </ion-button>
            <ion-button
              data-testid="recovery-generate-new"
              fill="clear"
              expand="block"
              class="after"
              :disabled="busy"
              @click="openRegenerate()"
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
              @click="openRegenerate()"
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
              @click="openRegenerate()"
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
            @click="revokeTrust()"
          >
            {{ $t('accounts.twoFactor.trusted.revoke') }}
          </ion-button>
        </div>
      </template>

      <div
        v-else-if="view === 'activate' && setup"
        data-testid="activate-view"
      >
        <div
          v-if="confirmWith"
          data-testid="activate-confirm"
        >
          <div class="auth-mark">
            <ion-icon
              class="auth-mark-icon"
              :icon="ICONS[confirmWith]"
              aria-hidden="true"
            />
          </div>
          <h2 class="auth-title">
            {{ $t('accounts.reauthenticate.title') }}
          </h2>
          <p
            class="auth-lead"
            data-testid="confirm-lead"
          >
            {{ confirmWith === 'password' ? $t('accounts.reauthenticate.passwordLead') : $t('accounts.reauthenticate.codeLead') }}
          </p>
          <form
            data-testid="confirm-form"
            novalidate
            @submit.prevent="confirmAndTurnOn()"
          >
            <div
              v-if="confirmWith === 'password'"
              class="field"
            >
              <ion-input
                v-model="confirmPassword"
                data-testid="confirm-password"
                mode="md"
                type="password"
                :label="$t('accounts.reauthenticate.password')"
                label-placement="floating"
                fill="outline"
                placeholder="••••••••••"
                autocomplete="current-password"
                :required="true"
                :error-text="fields.password"
                :class="{ 'ion-invalid': !!fields.password, 'ion-touched': !!fields.password }"
              >
                <ion-input-password-toggle slot="end" />
              </ion-input>
            </div>
            <CodeField
              v-else
              v-model="confirmCode"
              :error="fields.code"
            />
            <ion-button
              type="submit"
              data-testid="confirm-submit"
              color="primary"
              size="large"
              expand="block"
              class="submit"
              :disabled="busy"
            >
              {{ $t('accounts.reauthenticate.confirm') }}
            </ion-button>
          </form>
          <ion-button
            data-testid="confirm-cancel"
            fill="clear"
            expand="block"
            class="after"
            :disabled="busy"
            @click="cancelConfirm()"
          >
            {{ $t('accounts.twoFactor.activate.cancel') }}
          </ion-button>
        </div>
        <template v-else>
          <h2 class="auth-title">
            {{ $t('accounts.twoFactor.activate.title') }}
          </h2>
          <p
            class="auth-lead"
            data-testid="activate-lead"
          >
            {{ $t('accounts.twoFactor.activate.lead') }}
          </p>
          <img
            class="qr"
            data-testid="totp-qr"
            :src="qrDataUrl"
            :alt="$t('accounts.twoFactor.activate.qrAlt')"
          >
          <p
            class="auth-lead secret-lead"
            data-testid="activate-cant-scan"
          >
            {{ $t('accounts.twoFactor.activate.cantScan') }}
          </p>
          <code class="auth-secret">{{ setup.secret }}</code>
          <form
            data-testid="activate-form"
            novalidate
            @submit.prevent="turnOn()"
          >
            <CodeField
              v-model="code"
              :error="fields.code"
            />
            <ion-button
              type="submit"
              data-testid="activate-submit"
              color="primary"
              size="large"
              expand="block"
              class="submit"
              :disabled="busy"
            >
              {{ $t('accounts.twoFactor.activate.turnOn') }}
            </ion-button>
          </form>
          <ion-button
            data-testid="activate-cancel"
            fill="clear"
            expand="block"
            class="after"
            :disabled="busy"
            @click="show('index')"
          >
            {{ $t('accounts.twoFactor.activate.cancel') }}
          </ion-button>
        </template>
      </div>

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

      <div
        v-else-if="view === 'recoveryCodes'"
        data-testid="codes-view"
      >
        <div class="auth-mark">
          <ion-icon
            class="auth-mark-icon"
            :icon="ICONS.codes"
            aria-hidden="true"
          />
        </div>
        <h2 class="auth-title">
          {{ $t('accounts.twoFactor.codes.title') }}
        </h2>
        <p
          class="auth-lead"
          data-testid="codes-lead"
        >
          {{ $t('accounts.twoFactor.codes.lead') }}
        </p>
        <template v-if="recovery?.unusedCodeCount">
          <pre
            v-if="recovery.unusedCodes.length"
            class="recovery-codes"
            data-testid="codes-list"
          >{{ recovery.unusedCodes.join('\n') }}</pre>
          <p
            class="auth-lead"
            data-testid="codes-count"
          >
            {{ $t('accounts.twoFactor.codes.count', { unused: recovery.unusedCodeCount, total: recovery.totalCodeCount }) }}
          </p>
        </template>
        <div
          v-else
          class="non-field-error"
          data-testid="codes-none"
        >
          {{ $t('accounts.twoFactor.codes.noneLeft') }}
        </div>
        <ion-button
          v-if="recovery?.unusedCodes.length"
          data-testid="codes-download"
          fill="outline"
          expand="block"
          @click="download()"
        >
          {{ $t('accounts.twoFactor.codes.download') }}
        </ion-button>
        <ion-button
          data-testid="codes-generate"
          fill="outline"
          expand="block"
          class="after"
          :disabled="busy"
          @click="openRegenerate()"
        >
          {{ $t('accounts.twoFactor.codes.generateNew') }}
        </ion-button>
        <ion-button
          data-testid="codes-back"
          fill="clear"
          expand="block"
          class="after"
          :disabled="busy"
          @click="backToIndex()"
        >
          {{ $t('accounts.twoFactor.codes.back') }}
        </ion-button>
      </div>

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
        <router-link :to="LAUNCHER">
          {{ $t('accounts.twoFactor.backToSettings') }}
        </router-link>
      </p>
    </template>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
<style scoped>
/* The template's inline `style="margin-top:1rem;"` on «Can't scan?». */
.secret-lead {
  margin-top: 1rem;
}
</style>
