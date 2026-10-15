<script setup lang="ts">
// `/verify-email`: the one page of the codes allauth mails, over allauth.headless, in the frame of
// ERPlora/saas's `account/confirm_email_verification_code.html`. Every sign-in with a password waits here
// (Ioan, 2026-10-15) for one of two codes, read from the session's pending flow:
//   - `verify_email`: the code that proves the address of a sign-up (an unknown address on the launcher's
//     form creates the account) or of a login whose address was never proven (`…/auth/email/verify`);
//   - `login_by_code`: the sign-in code mailed to every other account, the second factor by email
//     (`…/auth/code/confirm`).
// Right, the visitor leaves the SPA for `next` or the launcher with a full page load, as the sign-in does,
// or goes on to the 2FA step when the account has the authenticator app. The address comes from the
// sign-in in the history state (allauth's session does not say it; never in the URL): after a reload in
// another tab the lead says «your email address». «Send a new code» asks allauth for another one where it
// sends one (`verify_email`; 409 when it sends no more); a sign-in code is renewed by signing in again
// (allauth resends it only with the passwordless sign-in on, which stays off). «Use a different email»
// ends the waiting login first: allauth would resume the stage otherwise (the template posted the logout
// for the same reason). A code sent with nothing waiting (expired, too many wrong codes) answers 409: back
// to the sign-in, which says why (`?notice=code_expired`) and mails a new code.
// Ionic keeps a page mounted when the visitor goes on and shows the same one again at the next sign-in
// (another address, maybe the other code): every arrival starts anew from the sign-in's hand-over and the
// session, with nothing of the last visit; «Use a different email» replaces the page, so Ionic drops it.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, createAllauthClient, type AuthState, type FieldErrors, useLiveClient } from '@erplora/ui/sdk';
import { ionIconSrc } from '@erplora/ui/shell';
import { IonButton, IonIcon, onIonViewWillEnter } from '@ionic/vue';
import { computed, onMounted, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import { type RouteLocationNormalizedLoaded, useRoute, useRouter } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import CodeField from '../components/CodeField.vue';
import { localNext } from '../next';
import { LAUNCHER } from '../paths';

const TWO_FACTOR = '/2fa/authenticate';
/** allauth's flow of a sign-up or login that waits for the code that proves its address. */
const EMAIL_FLOW = 'verify_email';
/** allauth's flow of a password login that waits for the sign-in code mailed to the account. */
const SIGN_IN_CODE_FLOW = 'login_by_code';
const CODE_FLOWS = [EMAIL_FLOW, SIGN_IN_CODE_FLOW];
/** `?notice=` of the sign-in when the code is gone (expired, too many wrong ones). */
const CODE_EXPIRED = { notice: 'code_expired' };
/** allauth's flow of a login that waits for its second factor. */
const SECOND_FACTOR_FLOW = 'mfa_authenticate';
const NON_FIELD = '__all__';
const MAIL_ICON = ionIconSrc('lucide:mail-check');

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = createAllauthClient(useLiveClient().config);

const code = shallowRef('');
const busy = shallowRef(false);
const fields = shallowRef<FieldErrors>({});
const failure = shallowRef('');
const notice = shallowRef('');
/** The address the sign-in typed, handed over in the history state. */
const email = shallowRef<string>();
/** The code the login waits for: the sign-in's word until the session says it; unknown, neither control. */
const flow = shallowRef<string>();
const signInCode = computed(() => flow.value === SIGN_IN_CODE_FLOW);

const next = computed(() => localNext(route.query.next));
const keepNext = computed(() => (next.value ? { next: next.value } : {}));

/** The sign-in's history state: the address it typed and the code it left waiting for. */
function readHandOver(): void {
  const handedOver = (router.options.history.state ?? {}) as Record<string, unknown>;
  email.value = typeof handedOver.email === 'string' && handedOver.email !== '' ? handedOver.email : undefined;
  flow.value = typeof handedOver.flow === 'string' && CODE_FLOWS.includes(handedOver.flow) ? handedOver.flow : undefined;
}
readHandOver();

function leave(): void {
  location.assign(next.value ?? LAUNCHER);
}

/** Signed in → on to `next`; the second factor next → its page; nothing waiting → the sign-in. */
function follow(state: AuthState): boolean {
  if (state.authenticated) leave();
  else if (state.pendingFlow === SECOND_FACTOR_FLOW) void router.replace({ path: TWO_FACTOR, query: keepNext.value });
  else if (!state.pendingFlow || !CODE_FLOWS.includes(state.pendingFlow)) void router.replace({ path: LAUNCHER, query: keepNext.value });
  else {
    flow.value = state.pendingFlow;
    return false;
  }
  return true;
}

/** What a refusal without a message of its own says. */
function fallback(error: unknown, otherwise: string): string {
  return error instanceof ApiError && error.status === 429 ? t('accounts.login.tooManyAttempts') : otherwise;
}

function reset(): void {
  fields.value = {};
  failure.value = '';
  notice.value = '';
}

/** The arrival last read (its navigation's route): Ionic announces the first one too, around the mount. */
let arrival: RouteLocationNormalizedLoaded | undefined;

/** Each arrival on the page: the sign-in's hand-over, nothing of the last visit, and the session followed. */
async function arrive(): Promise<void> {
  if (arrival === router.currentRoute.value) return;
  arrival = router.currentRoute.value;
  document.title = `${t('accounts.verifyEmail.title')} - ERPlora Cloud`;
  readHandOver();
  code.value = '';
  reset();
  try {
    follow(await auth.getSession());
  } catch {
    failure.value = t('accounts.login.failed');
  }
}
onMounted(arrive);
onIonViewWillEnter(arrive);

async function submit(): Promise<void> {
  busy.value = true;
  reset();
  try {
    const state = signInCode.value ? await auth.confirmLoginCode(code.value) : await auth.verifyEmail(code.value);
    if (!follow(state)) failure.value = t('accounts.login.failed');
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      await router.replace({ path: LAUNCHER, query: { ...keepNext.value, ...CODE_EXPIRED } });
    } else if (error instanceof ApiError && error.fields) {
      fields.value = error.fields;
      failure.value = error.fields[NON_FIELD] ?? '';
    } else {
      failure.value = fallback(error, t('accounts.login.failed'));
    }
  } finally {
    busy.value = false;
  }
}

async function resend(): Promise<void> {
  busy.value = true;
  reset();
  try {
    await auth.resendEmailVerification();
    notice.value = t('accounts.verifyEmail.resent');
  } catch (error) {
    // 409: no more codes for this sign-up, or nothing waits any more (then `follow` leaves).
    if (error instanceof ApiError && error.status === 409 && (await followSession())) return;
    failure.value = fallback(error, t('accounts.verifyEmail.resendFailed'));
  } finally {
    busy.value = false;
  }
}

/** Reads the session and follows it: `true` when the page was left, `false` when it still waits (or unknown). */
async function followSession(): Promise<boolean> {
  try {
    return follow(await auth.getSession());
  } catch {
    return false;
  }
}

async function useDifferentEmail(): Promise<void> {
  busy.value = true;
  reset();
  try {
    await auth.logout();
    await router.replace({ path: LAUNCHER, query: keepNext.value });
  } catch {
    failure.value = t('accounts.login.failed');
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AuthShell :subtitle="$t('accounts.login.subtitle')">
    <div class="auth-mark">
      <ion-icon
        class="auth-mark-icon"
        :icon="MAIL_ICON"
        aria-hidden="true"
      />
    </div>
    <h2 class="auth-title">
      {{ $t('accounts.verifyEmail.title') }}
    </h2>
    <p class="auth-lead">
      {{ email ? $t('accounts.verifyEmail.sentTo', { recipient: email }) : $t('accounts.verifyEmail.sent') }}
    </p>

    <InlineFeedback
      v-if="notice"
      tone="success"
      class="notice"
      data-testid="verify-email-notice"
    >
      {{ notice }}
    </InlineFeedback>
    <div
      v-if="failure"
      class="non-field-error"
      role="alert"
    >
      {{ failure }}
    </div>

    <form
      data-testid="verify-email-form"
      novalidate
      @submit.prevent="submit"
    >
      <!-- allauth names the field `key` for the address's code and `code` for the sign-in code. -->
      <CodeField
        v-model="code"
        :error="fields.key ?? fields.code"
      />
      <ion-button
        type="submit"
        data-testid="verify-email-submit"
        color="primary"
        size="large"
        expand="block"
        class="submit"
        :disabled="busy"
      >
        {{ $t('accounts.verifyEmail.verify') }}
      </ion-button>
    </form>

    <p
      v-if="signInCode"
      class="help"
      data-testid="verify-email-help"
    >
      {{ $t('accounts.verifyEmail.signInCodeHelp') }}
    </p>
    <ion-button
      v-else-if="flow === EMAIL_FLOW"
      data-testid="verify-email-resend"
      fill="clear"
      expand="block"
      class="after"
      :disabled="busy"
      @click="resend"
    >
      {{ $t('accounts.verifyEmail.resend') }}
    </ion-button>
    <ion-button
      data-testid="verify-email-other"
      fill="clear"
      expand="block"
      :disabled="busy"
      @click="useDifferentEmail"
    >
      {{ $t('accounts.verifyEmail.useDifferentEmail') }}
    </ion-button>

    <template #foot>
      <p class="foot">
        {{ $t('accounts.login.agree') }}
        <a href="https://erplora.com/legal/terms/">{{ $t('accounts.login.terms') }}</a>
        &amp;
        <a href="https://erplora.com/legal/privacy/">{{ $t('accounts.login.privacy') }}</a>.
      </p>
    </template>
  </AuthShell>
</template>

<style scoped src="../components/auth-card.css"></style>
<style scoped>
.notice {
  margin-bottom: 0.85rem;
}
.help {
  margin: 1rem 0 0.25rem;
  font-size: 13px;
  text-align: center;
  color: color-mix(in oklch, var(--ion-text-color) 60%, transparent);
}
</style>
