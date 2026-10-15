<script setup lang="ts">
// `/login/error?code=…`: the one page of every refused sign-in or jump to a hub. Django redirects
// here (`handoff.hub_login`, the SocialAccountAdapter, allauth's own error addresses) and the page
// says what the template of each case said, with their msgids (`../locale`):
//   - invalid_hub          → `accounts/hub_link_invalid.html` (nothing that came in is echoed);
//   - not_a_member + hub   → `accounts/hub_access_denied.html` (the hub's HOST, never its business);
//   - authentication_error → allauth's `socialaccount/authentication_error.html`;
//   - login_cancelled      → allauth's `socialaccount/login_cancelled.html`;
//   - google_link_refused  → the refused «connect» of Google (`SocialAccountAdapter.pre_social_login`): Google is
//                            linked by signing in with it, the message the adapter used to leave on the launcher.
// The way back is the sign-in (keeping `next`), or the launcher when there is a session. A code it
// does not know, or without what its text needs, is a failed Google sign-in (so is the old
// `google_no_account`: an unknown Google address now creates its account).
import { useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';

import AuthShell from '../components/AuthShell.vue';
import { localNext } from '../next';
import { LAUNCHER } from '../paths';

type Code = 'invalid_hub' | 'not_a_member' | 'authentication_error' | 'login_cancelled' | 'google_link_refused';

interface Copy {
  /** Catalogue keys under `accounts.loginError.<copy>`; `title` and `badge` only where the template had them. */
  copy: string;
  title?: boolean;
  badge?: boolean;
  action: 'home' | 'backToSignIn';
  /** The hub pages' links: support, and back to the hub the person came from (not_a_member). */
  links?: boolean;
}

const COPY: Record<Code, Copy> = {
  invalid_hub: { copy: 'invalidHub', title: true, badge: true, action: 'home', links: true },
  not_a_member: { copy: 'notAMember', title: true, badge: true, action: 'home', links: true },
  authentication_error: { copy: 'authenticationError', action: 'backToSignIn' },
  login_cancelled: { copy: 'loginCancelled', action: 'backToSignIn' },
  google_link_refused: { copy: 'googleLinkRefused', action: 'home' },
};
/** The codes that need nothing else in the URL to be told. */
const PLAIN_CODES: readonly Code[] = ['invalid_hub', 'login_cancelled', 'google_link_refused'];

/**
 * First label of a hub's host: one DNS label, the format of `live.slugs.HUB_SLUG_RE` (shared by
 * hub-next and saas-next). Only the format: it keeps anything else from being echoed as a host;
 * the reserved names are refused by Django, which never sends them here.
 */
const HUB_SLUG = /^[a-z0-9]([a-z0-9-]{1,61}[a-z0-9])?$/;
const SUPPORT = 'mailto:info@erplora.com';

const { t } = useI18n();
const route = useRoute();
const session = useSession();
const client = useLiveClient();

function param(name: string): string | undefined {
  const value = route.query[name];
  return typeof value === 'string' && value !== '' ? value : undefined;
}

/** `https://a.erplora.com` of `?hub=a`, from the server's pattern (spa-config); never from the URL. */
const hubOrigin = computed(() => {
  const slug = param('hub');
  const pattern = client.config.hubOrigin;
  return slug && pattern && HUB_SLUG.test(slug) ? pattern.replace('{slug}', slug) : undefined;
});

const code = computed<Code>(() => {
  const asked = param('code');
  if (asked === 'not_a_member') return hubOrigin.value ? 'not_a_member' : 'invalid_hub';
  return PLAIN_CODES.find((plain) => plain === asked) ?? 'authentication_error';
});
const copy = computed(() => COPY[code.value]);
const key = (name: string) => `accounts.loginError.${copy.value.copy}.${name}`;

const message = computed(() => t(key('message'), { hub_host: hubOrigin.value?.replace(/^[a-z][a-z0-9+.-]*:\/\//, '') }));

/** Back to the sign-in, keeping where the person was going; with a session, the launcher. */
const back = computed(() => {
  if (session.user.value) return LAUNCHER;
  const next = localNext(param('next'));
  return next ? `${LAUNCHER}?next=${encodeURIComponent(next)}` : LAUNCHER;
});

onMounted(() => {
  const title = copy.value.title ? key('title') : key('heading');
  document.title = `${t(title)} - ERPlora Cloud`;
});
</script>

<template>
  <AuthShell :subtitle="$t('accounts.login.subtitle')">
    <p
      v-if="copy.badge"
      class="badge"
      data-testid="login-error-badge"
    >
      {{ $t(key('badge')) }}
    </p>
    <h2 class="auth-title">
      {{ $t(key('heading')) }}
    </h2>
    <p class="auth-lead">
      {{ message }}
    </p>
    <ion-button
      data-testid="login-error-action"
      :href="back"
      color="primary"
      size="large"
      expand="block"
    >
      {{ $t(`accounts.loginError.${copy.action}`) }}
    </ion-button>
    <div
      v-if="copy.links"
      class="links"
      data-testid="login-error-links"
    >
      <a
        v-if="code === 'not_a_member'"
        :href="`${hubOrigin}/`"
      >{{ $t('accounts.loginError.backToHub') }}</a>
      <a :href="SUPPORT">{{ $t('accounts.loginError.contactSupport') }}</a>
    </div>
  </AuthShell>
</template>

<style scoped>
/* The «400 · Invalid link» line of the error templates (`error-page-fallback__code`), in the auth card. */
.badge {
  margin: 0;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  text-align: center;
  color: color-mix(in oklch, var(--ion-text-color) 50%, transparent);
}
.links {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
  margin-top: 1rem;
  font-size: 13px;
}
.links a {
  color: var(--ion-color-primary);
}
.links a:hover {
  text-decoration: underline;
}
</style>
